"""Map CINDER v1.1.2 8x8 closure conditioning and 2x2 stick-root geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import integrate_hybrid
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTShiftConstraint,
)
from cinder.model.cvt.contact import (
    ContactInterface,
    ContactTractionUtilization,
    EngagedContactMode,
)
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system import CVTState
from cinder.results.inspection import inspect_cvt_state

from conditioning_math import finite_difference_jacobian

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
SPEC_FILE = HERE / "study.json"
ARTIFACTS = HERE / "artifacts"
EXPECTED_CINDER_VERSION = "1.1.2"


@dataclass(frozen=True)
class FrozenSample:
    time: float
    full_state: np.ndarray
    composed_mode: Any
    cvt_state: CVTState


@dataclass(frozen=True)
class ReferenceRun:
    name: str
    decoded: Any
    result: Any
    samples: tuple[FrozenSample, ...]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use reduced map and multi-start resolution for a fast structural preview.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any, *, allow_nan: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=allow_nan) + "\n",
        encoding="utf-8",
    )


def write_rows(path: Path, rows: list[dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def verify_environment():
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__} "
            f"at {Path(cinder.__file__).resolve()}."
        )


def validate_and_decode(document):
    report = validate_simulation_case_document(document)
    if not report.is_valid:
        for finding in report.findings:
            print(
                f"[{finding.severity}] "
                f"{finding.document_path or '/'}: {finding.message}"
            )
        raise RuntimeError("Resolved conditioning-study input failed validation.")
    return decode_simulation_case_document(document)


def uniform_times(start, end, step):
    if end <= start:
        return np.asarray([start], dtype=float)
    values = start + step * np.arange(int(math.floor((end - start) / step)) + 1)
    if end - values[-1] > 1e-12:
        values = np.append(values, end)
    else:
        values[-1] = end
    return values


def build_reference(spec, run_name: str) -> ReferenceRun:
    base = (HERE / spec["base_document"]).resolve()
    if not base.is_file():
        raise FileNotFoundError(
            f"Frozen default is missing: {base}. "
            "This study intentionally depends only on the release defaults folder."
        )
    document = copy.deepcopy(load_json(base))
    cfg = spec["reference_runs"][run_name]
    document["scenario"]["time_span_s"] = list(cfg["time_span_s"])
    for key, value in cfg["integrator"].items():
        document["execution"]["integrator"][key] = value
    document["execution"]["integrator"]["retain_dense_output"] = True

    if "road_grade_segments" in cfg:
        document["shaft_boundaries"]["secondary"]["road_profile"] = {
            "kind": "piecewise_constant_grade",
            "segments": [
                {
                    "start_distance_m": float(row["start_distance_m"]),
                    "grade_angle_rad": math.radians(float(row["grade_angle_deg"])),
                }
                for row in cfg["road_grade_segments"]
            ],
        }

    decoded = validate_and_decode(document)
    result = integrate_hybrid(
        system=decoded.system,
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
    )

    samples = []
    step = float(cfg["sample_step_s"])
    for segment in result.segments:
        times = uniform_times(segment.start_time, segment.end_time, step)
        states = (
            segment.dense_state_at(times)
            if segment.has_dense_output
            else segment.state
        )
        if not segment.has_dense_output:
            times = segment.time
        for j, t in enumerate(times):
            full = np.asarray(states[:, j], dtype=float)
            cvt = CVTState.from_vector(decoded.system.layout.view(full, "cvt"))
            samples.append(
                FrozenSample(
                    time=float(t),
                    full_state=full,
                    composed_mode=segment.mode,
                    cvt_state=cvt,
                )
            )
    return ReferenceRun(
        name=run_name,
        decoded=decoded,
        result=result,
        samples=tuple(samples),
    )


def reconstruct(ref: ReferenceRun, sample: FrozenSample, *, closure_audit: bool):
    boundaries = ref.decoded.system._shaft_boundaries(
        time=sample.time,
        state=sample.full_state,
    )
    return inspect_cvt_state(
        system=ref.decoded.system.cvt,
        time=sample.time,
        vector=ref.decoded.system.layout.view(sample.full_state, "cvt"),
        mode=sample.composed_mode.cvt,
        shaft_boundaries=boundaries,
        include_closure_audit=closure_audit,
    )


def is_stick_stick(sample: FrozenSample) -> bool:
    mode = sample.composed_mode.cvt
    return (
        mode.engagement is CVTEngagementState.ENGAGED
        and mode.contact_regime is not None
        and mode.contact_regime.mode is EngagedContactMode.STICK_STICK
    )


def shift_fraction(ref: ReferenceRun, sample: FrozenSample) -> float:
    spec = ref.decoded.system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift
    return (sample.cvt_state.shift_position - spec.deadzone_shift) / span


def select_states(launch: ReferenceRun, disturbed: ReferenceRun | None):
    candidates = [s for s in launch.samples if is_stick_stick(s)]
    selected = []

    low = [
        s for s in candidates
        if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT
    ]
    if low:
        selected.append(("low_ratio_seat", launch, max(low, key=lambda s: s.time)))

    free = [
        s for s in candidates
        if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.FREE
    ]
    if free:
        mid = min(free, key=lambda s: abs(shift_fraction(launch, s) - 0.50))
        late = min(free, key=lambda s: abs(shift_fraction(launch, s) - 0.85))
        selected.append(("mid_shift", launch, mid))
        if late is not mid:
            selected.append(("late_shift", launch, late))

    upper = [
        s for s in candidates
        if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.UPPER_STOP
    ]
    if upper:
        selected.append(("upper_stop", launch, upper[len(upper)//2]))

    if disturbed is not None:
        dfree = [
            s for s in disturbed.samples
            if is_stick_stick(s)
            and s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.FREE
        ]
        if dfree:
            chosen = min(dfree, key=lambda s: s.cvt_state.shift_speed)
            selected.append(("load_disturbed_or_backshift", disturbed, chosen))

    # De-duplicate source/time points while keeping the most descriptive first label.
    out, seen = [], set()
    for label, ref, sample in selected:
        key = (ref.name, round(sample.time, 12))
        if key in seen:
            continue
        seen.add(key)
        out.append((label, ref, sample))
    return out


def engaged_constraint(sample: FrozenSample):
    value = sample.composed_mode.cvt.shift_constraint
    if value is CVTShiftConstraint.FREE:
        return EngagedShiftConstraint.FREE
    if value is CVTShiftConstraint.LOW_RATIO_SEAT:
        return EngagedShiftConstraint.LOW_RATIO_SEAT
    if value is CVTShiftConstraint.UPPER_STOP:
        return EngagedShiftConstraint.UPPER_STOP
    raise ValueError(value)


def domain_bounds(ref: ReferenceRun, domain: str):
    law = ref.decoded.system.cvt.traction_law
    p = law.primary_static_interval
    s = law.secondary_static_interval
    if domain == "physical":
        return p.lower, p.upper, s.lower, s.upper
    physical = max(abs(p.lower), abs(p.upper), abs(s.lower), abs(s.upper))
    if domain == "expanded":
        half = max(2.5, 4.0 * physical)
        return -half, half, -half, half
    if domain == "broad":
        return -10.0, 10.0, -10.0, 10.0
    raise ValueError(domain)


def actual_root_metrics(label, ref, sample):
    inspection = reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    audit = inspection.closure_audit
    if contact is None or audit is None:
        raise RuntimeError("Selected state did not reconstruct an engaged closure.")

    branch = contact.branch_result
    jac = getattr(branch, "jacobian", None)
    if jac is None:
        sigma_min = sigma_max = kappa = determinant = float("nan")
    else:
        singular = np.linalg.svd(np.asarray(jac, dtype=float), compute_uv=False)
        sigma_max = float(singular[0])
        sigma_min = float(singular[-1])
        kappa = sigma_max / sigma_min if sigma_min > 0 else float("inf")
        determinant = float(np.linalg.det(jac))

    u = contact.traction_utilization
    law = ref.decoded.system.cvt.traction_law
    return {
        "label": label,
        "source_run": ref.name,
        "time_s": sample.time,
        "shift_mm": 1000.0 * sample.cvt_state.shift_position,
        "shift_speed_mm_s": 1000.0 * sample.cvt_state.shift_speed,
        "shift_constraint": sample.composed_mode.cvt.shift_constraint.value,
        "contact_mode": contact.mode.value,
        "lambda_p": u.primary_lambda,
        "lambda_s": u.secondary_lambda,
        "primary_static_margin": law.static_margin_at(ContactInterface.PRIMARY, u.primary_lambda),
        "secondary_static_margin": law.static_margin_at(ContactInterface.SECONDARY, u.secondary_lambda),
        "A_condition_raw": audit.condition_number,
        "A_condition_scaled": audit.scaled_condition_number,
        "A_rank": audit.matrix_rank,
        "A_max_abs_equation_residual": audit.max_abs_equation_residual,
        "J_sigma_min": sigma_min,
        "J_sigma_max": sigma_max,
        "J_condition": kappa,
        "J_determinant": determinant,
        "N_p": contact.normal_primary,
        "N_s": contact.normal_secondary,
    }


def build_map(ref, sample, domain, samples):
    inspection = reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    if contact is None:
        raise RuntimeError("Conditioning map requires engaged contact.")
    closure = EngagedContactClosure(
        snapshot=contact.snapshot,
        shift_constraint=engaged_constraint(sample),
    )

    p0, p1, s0, s1 = domain_bounds(ref, domain)
    lp = np.linspace(p0, p1, samples)
    ls = np.linspace(s0, s1, samples)
    shape = (samples, samples)
    arrays = {
        key: np.full(shape, np.nan)
        for key in (
            "R_p", "R_s", "cond_A_raw", "cond_A_scaled", "rank_A",
            "N_p", "N_s", "tau_p", "tau_s"
        )
    }

    solved = 0
    for i, lam_s in enumerate(ls):
        if i % max(1, samples // 10) == 0:
            print(f"      row {i+1}/{samples}")
        for j, lam_p in enumerate(lp):
            try:
                trial = closure.evaluate_trial(
                    traction_utilization=ContactTractionUtilization(
                        primary_lambda=float(lam_p),
                        secondary_lambda=float(lam_s),
                    ),
                    maximum_closure_condition_number=None,
                    capture_diagnostics=True,
                )
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                continue
            audit = trial.closure
            motion = trial.relative_motion
            arrays["R_p"][i, j] = motion.primary_relative_acceleration
            arrays["R_s"][i, j] = motion.secondary_relative_acceleration
            arrays["cond_A_raw"][i, j] = audit.condition_number
            arrays["cond_A_scaled"][i, j] = audit.scaled_condition_number
            arrays["rank_A"][i, j] = audit.matrix_rank
            arrays["N_p"][i, j] = audit.unknowns.primary_normal_resultant
            arrays["N_s"][i, j] = audit.unknowns.secondary_normal_resultant
            arrays["tau_p"][i, j] = audit.unknowns.primary_torque
            arrays["tau_s"][i, j] = audit.unknowns.secondary_torque
            solved += 1

    arrays["R_norm"] = np.hypot(arrays["R_p"], arrays["R_s"])
    smin, smax, kappa, det = finite_difference_jacobian(
        lp, ls, arrays["R_p"], arrays["R_s"]
    )
    arrays["sigma_min_J"] = smin
    arrays["sigma_max_J"] = smax
    arrays["kappa_J"] = kappa
    arrays["det_J"] = det
    arrays["lambda_p"] = lp
    arrays["lambda_s"] = ls
    arrays["solved_count"] = solved
    arrays["total_count"] = samples * samples
    return arrays


def multistart(ref, sample, n, cluster_tol):
    inspection = reconstruct(ref, sample, closure_audit=False)
    contact = inspection.contact
    if contact is None:
        return [], []
    closure = EngagedContactClosure(
        snapshot=contact.snapshot,
        shift_constraint=engaged_constraint(sample),
    )
    law = ref.decoded.system.cvt.traction_law
    base = ref.decoded.system.cvt.solve_settings
    p = np.linspace(law.primary_static_interval.lower, law.primary_static_interval.upper, n)
    s = np.linspace(law.secondary_static_interval.lower, law.secondary_static_interval.upper, n)

    roots = []
    rows = []
    for lam_s in s:
        for lam_p in p:
            row = {
                "start_lambda_p": float(lam_p),
                "start_lambda_s": float(lam_s),
                "optimizer_success": False,
                "accepted": False,
                "statically_admissible": False,
                "root_lambda_p": float("nan"),
                "root_lambda_s": float("nan"),
                "root_cluster": -1,
                "residual_norm": float("nan"),
                "jacobian_condition": float("nan"),
                "function_evaluations": -1,
            }
            try:
                settings = replace(
                    base,
                    initial_guess=ContactTractionUtilization(
                        primary_lambda=float(lam_p),
                        secondary_lambda=float(lam_s),
                    ),
                )
                solved = closure.solve_stick_stick(settings=settings)
                root = np.asarray(
                    [
                        solved.traction_utilization.primary_lambda,
                        solved.traction_utilization.secondary_lambda,
                    ],
                    dtype=float,
                )
                cluster = -1
                if solved.accepted:
                    for idx, existing in enumerate(roots):
                        if np.linalg.norm(root - existing) <= cluster_tol:
                            cluster = idx
                            break
                    if cluster < 0:
                        cluster = len(roots)
                        roots.append(root)
                row.update(
                    {
                        "optimizer_success": bool(solved.optimizer_success),
                        "accepted": bool(solved.accepted),
                        "statically_admissible": bool(
                            solved.sticking_interfaces_are_statically_admissible(
                                traction_law=law
                            )
                        ),
                        "root_lambda_p": float(root[0]),
                        "root_lambda_s": float(root[1]),
                        "root_cluster": cluster,
                        "residual_norm": float(np.linalg.norm(solved.sticking_residuals)),
                        "jacobian_condition": float(solved.jacobian_condition_number),
                        "function_evaluations": int(solved.function_evaluations),
                    }
                )
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                pass
            rows.append(row)
    return rows, roots


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99)), lo * 1.01)
    return lo, hi


def signed_limit(values):
    a = np.abs(np.asarray(values, dtype=float))
    a = a[np.isfinite(a)]
    return max(float(np.percentile(a, 99)) if a.size else 1.0, 1e-12)


def plot_map(data, actual, label, domain, path):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    normal = np.maximum(np.abs(data["N_p"]), np.abs(data["N_s"]))
    rp_lim = signed_limit(data["R_p"])
    rs_lim = signed_limit(data["R_s"])
    rn_lo, rn_hi = positive_limits(data["R_norm"])
    ca_lo, ca_hi = positive_limits(data["cond_A_scaled"])
    sm_lo, sm_hi = positive_limits(data["sigma_min_J"])
    kj_lo, kj_hi = positive_limits(data["kappa_J"])
    det_lim = signed_limit(data["det_J"])
    n_lo, n_hi = positive_limits(normal)

    panels = [
        ("R_p", r"Primary stick residual $R_p$", SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim), data["R_p"]),
        ("R_s", r"Secondary stick residual $R_s$", SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim), data["R_s"]),
        ("R_norm", r"Residual norm $\|\mathbf{R}\|_2$", LogNorm(vmin=rn_lo, vmax=rn_hi), data["R_norm"]),
        ("cond_A_scaled", r"Equilibrated 8×8 $\kappa(A)$", LogNorm(vmin=ca_lo, vmax=ca_hi), data["cond_A_scaled"]),
        ("sigma_min_J", r"$\sigma_{\min}(J_R)$", LogNorm(vmin=sm_lo, vmax=sm_hi), data["sigma_min_J"]),
        ("kappa_J", r"$\kappa(J_R)$", LogNorm(vmin=kj_lo, vmax=kj_hi), data["kappa_J"]),
        ("det_J", r"Signed $\det(J_R)$", TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim), data["det_J"]),
        ("normal", r"max$(|N_p|,|N_s|)$", LogNorm(vmin=n_lo, vmax=n_hi), normal),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9.5), constrained_layout=True)
    for ax, (key, title, norm, values) in zip(axes.ravel(), panels):
        im = ax.pcolormesh(LP, LS, values, shading="auto", norm=norm)
        if key == "R_norm":
            with np.errstate(all="ignore"):
                try:
                    ax.contour(LP, LS, data["R_p"], levels=[0.0], linewidths=1.2)
                    ax.contour(LP, LS, data["R_s"], levels=[0.0], linewidths=1.2, linestyles="--")
                except ValueError:
                    pass
        ax.plot(actual["lambda_p"], actual["lambda_s"], marker="x", markersize=8, mew=2)
        ax.set_xlabel(r"$\lambda_p$")
        ax.set_ylabel(r"$\lambda_s$")
        ax.set_title(title)
        fig.colorbar(im, ax=ax, shrink=0.82)
    fig.suptitle(f"{label}: {domain} lambda domain")
    fig.savefig(path, dpi=175)
    plt.close(fig)


def plot_slices(data, actual, label, path):
    lp, ls = data["lambda_p"], data["lambda_s"]
    i = int(np.argmin(np.abs(ls - actual["lambda_s"])))
    j = int(np.argmin(np.abs(lp - actual["lambda_p"])))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)

    axes[0,0].plot(lp, data["R_p"][i,:], label=r"$R_p$")
    axes[0,0].plot(lp, data["R_s"][i,:], label=r"$R_s$")
    axes[0,0].axhline(0.0, linewidth=1.0)
    axes[0,0].axvline(actual["lambda_p"], linewidth=1.0)
    axes[0,0].set_xlabel(r"$\lambda_p$")
    axes[0,0].set_ylabel("Residual [m/s²]")
    axes[0,0].set_title(rf"Residual slice at $\lambda_s\approx{ls[i]:.3g}$")
    axes[0,0].grid(True, alpha=0.25)
    axes[0,0].legend()

    axes[0,1].plot(lp, data["N_p"][i,:], label=r"$N_p$")
    axes[0,1].plot(lp, data["N_s"][i,:], label=r"$N_s$")
    axes[0,1].axhline(0.0, linewidth=1.0)
    axes[0,1].axvline(actual["lambda_p"], linewidth=1.0)
    axes[0,1].set_xlabel(r"$\lambda_p$")
    axes[0,1].set_ylabel("Normal resultant [N]")
    axes[0,1].set_title("Normal-force response on same slice")
    axes[0,1].grid(True, alpha=0.25)
    axes[0,1].legend()

    axes[1,0].plot(ls, data["R_p"][:,j], label=r"$R_p$")
    axes[1,0].plot(ls, data["R_s"][:,j], label=r"$R_s$")
    axes[1,0].axhline(0.0, linewidth=1.0)
    axes[1,0].axvline(actual["lambda_s"], linewidth=1.0)
    axes[1,0].set_xlabel(r"$\lambda_s$")
    axes[1,0].set_ylabel("Residual [m/s²]")
    axes[1,0].set_title(rf"Residual slice at $\lambda_p\approx{lp[j]:.3g}$")
    axes[1,0].grid(True, alpha=0.25)
    axes[1,0].legend()

    axes[1,1].plot(ls, data["N_p"][:,j], label=r"$N_p$")
    axes[1,1].plot(ls, data["N_s"][:,j], label=r"$N_s$")
    axes[1,1].axhline(0.0, linewidth=1.0)
    axes[1,1].axvline(actual["lambda_s"], linewidth=1.0)
    axes[1,1].set_xlabel(r"$\lambda_s$")
    axes[1,1].set_ylabel("Normal resultant [N]")
    axes[1,1].set_title("Normal-force response on same slice")
    axes[1,1].grid(True, alpha=0.25)
    axes[1,1].legend()

    fig.suptitle(f"{label}: broad-domain slices through the physical root")
    fig.savefig(path, dpi=175)
    plt.close(fig)


def plot_multistart(rows, roots, label, path):
    fig, ax = plt.subplots(figsize=(7.3, 6.2))
    failed = [r for r in rows if not r["accepted"]]
    accepted = [r for r in rows if r["accepted"]]
    if failed:
        ax.scatter(
            [r["start_lambda_p"] for r in failed],
            [r["start_lambda_s"] for r in failed],
            marker="x",
            label="Not accepted",
        )
    if accepted:
        for cluster in sorted(set(int(r["root_cluster"]) for r in accepted)):
            group = [r for r in accepted if int(r["root_cluster"]) == cluster]
            ax.scatter(
                [r["start_lambda_p"] for r in group],
                [r["start_lambda_s"] for r in group],
                label=f"Accepted root {cluster+1}",
            )
    for root in roots:
        ax.plot(root[0], root[1], marker="*", markersize=14)
    ax.set_xlabel(r"Initial $\lambda_p$")
    ax.set_ylabel(r"Initial $\lambda_s$")
    ax.set_title(f"{label}: stick-root multi-start basin")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def feature_rows(data, label):
    rows = []
    lp, ls = data["lambda_p"], data["lambda_s"]

    def point(feature, score, choose="max"):
        score = np.asarray(score, dtype=float)
        finite = np.isfinite(score)
        if not np.any(finite):
            return
        ranked = np.where(
            finite,
            score,
            np.inf if choose == "min" else -np.inf,
        )
        flat = int(np.argmin(ranked) if choose == "min" else np.argmax(ranked))
        i, j = np.unravel_index(flat, ranked.shape)
        row = {
            "state": label,
            "feature": feature,
            "lambda_p": float(lp[j]),
            "lambda_s": float(ls[i]),
        }
        for key in (
            "R_p", "R_s", "R_norm",
            "cond_A_raw", "cond_A_scaled", "rank_A",
            "sigma_min_J", "sigma_max_J", "kappa_J", "det_J",
            "N_p", "N_s", "tau_p", "tau_s",
        ):
            row[key] = float(data[key][i,j])
        rows.append(row)

    point("maximum_scaled_8x8_condition", data["cond_A_scaled"])
    point("maximum_stick_jacobian_condition", data["kappa_J"])
    point("minimum_stick_jacobian_sigma_min", data["sigma_min_J"], choose="min")
    point("maximum_abs_primary_normal", np.abs(data["N_p"]))
    point("maximum_abs_secondary_normal", np.abs(data["N_s"]))
    return rows


def main():
    args = parse_args()
    verify_environment()
    spec = load_json(SPEC_FILE)
    base_path = (HERE / spec["base_document"]).resolve()

    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)

    print("Running baseline launch reference...")
    launch = build_reference(spec, "launch")

    disturbed = None
    disturbed_status = {"available": False, "error": None}
    print("Running mild load-disturbed reference...")
    try:
        disturbed = build_reference(spec, "load_disturbed")
        disturbed_status["available"] = True
    except Exception as exc:
        disturbed_status["error"] = f"{type(exc).__name__}: {exc}"
        print("  load-disturbed reference unavailable:", disturbed_status["error"])

    states = select_states(launch, disturbed)
    if len(states) < 3:
        raise RuntimeError(
            f"Only {len(states)} representative stick-stick states found; need at least three."
        )

    actual_rows = [
        actual_root_metrics(label, ref, sample)
        for label, ref, sample in states
    ]
    write_rows(ARTIFACTS / "representative_states.csv", actual_rows)

    multistart_all = []
    multistart_summary = []
    domain_summary = []
    broad_features = []

    for (label, ref, sample), actual in zip(states, actual_rows):
        state_dir = ARTIFACTS / "states" / label
        state_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nState: {label} at t={sample.time:.6f}s")

        n_start = int(spec["multistart"]["samples_per_axis"])
        if args.quick:
            n_start = 5
        ms_rows, roots = multistart(
            ref,
            sample,
            n_start,
            float(spec["multistart"]["root_cluster_tolerance"]),
        )
        for row in ms_rows:
            row["state"] = label
        multistart_all.extend(ms_rows)
        multistart_summary.append(
            {
                "state": label,
                "start_count": len(ms_rows),
                "accepted_count": sum(bool(r["accepted"]) for r in ms_rows),
                "statically_admissible_accepted_count": sum(
                    bool(r["accepted"]) and bool(r["statically_admissible"])
                    for r in ms_rows
                ),
                "distinct_accepted_roots": len(roots),
                "all_accepted_one_root": len(roots) == 1,
            }
        )
        plot_multistart(ms_rows, roots, label, state_dir / "multistart_basin.png")

        for domain in ("physical", "expanded", "broad"):
            n = int(spec["lambda_domains"][domain]["samples"])
            if args.quick:
                n = max(51, (n + 1) // 2)
                if n % 2 == 0:
                    n += 1
            print(f"  {domain}: {n}×{n}")
            data = build_map(ref, sample, domain, n)
            np.savez_compressed(
                state_dir / f"{domain}_map.npz",
                **{k: v for k, v in data.items() if isinstance(v, np.ndarray)},
            )
            plot_map(
                data, actual, label, domain,
                state_dir / f"{domain}_conditioning_map.png",
            )

            finite_A = data["cond_A_scaled"][np.isfinite(data["cond_A_scaled"])]
            finite_J = data["kappa_J"][np.isfinite(data["kappa_J"])]
            finite_s = data["sigma_min_J"][np.isfinite(data["sigma_min_J"])]
            domain_summary.append(
                {
                    "state": label,
                    "domain": domain,
                    "samples_per_axis": n,
                    "solved_fraction": data["solved_count"] / data["total_count"],
                    "A_scaled_condition_max": float(np.max(finite_A)) if finite_A.size else float("nan"),
                    "A_scaled_condition_p99": float(np.percentile(finite_A, 99)) if finite_A.size else float("nan"),
                    "J_condition_max": float(np.max(finite_J)) if finite_J.size else float("nan"),
                    "J_condition_p99": float(np.percentile(finite_J, 99)) if finite_J.size else float("nan"),
                    "J_sigma_min_min": float(np.min(finite_s)) if finite_s.size else float("nan"),
                    "rank_deficient_grid_points": int(
                        np.count_nonzero(
                            np.isfinite(data["rank_A"]) & (data["rank_A"] < 8)
                        )
                    ),
                }
            )
            if domain == "broad":
                broad_features.extend(feature_rows(data, label))
                plot_slices(
                    data, actual, label,
                    state_dir / "broad_root_slices.png",
                )

    write_rows(ARTIFACTS / "multistart_results.csv", multistart_all)
    write_rows(ARTIFACTS / "multistart_summary.csv", multistart_summary)
    write_rows(ARTIFACTS / "domain_conditioning_summary.csv", domain_summary)
    write_rows(ARTIFACTS / "broad_feature_peaks.csv", broad_features)

    physical = [r for r in domain_summary if r["domain"] == "physical"]
    overall = {
        "all_actual_A_rank_8": all(int(r["A_rank"]) == 8 for r in actual_rows),
        "all_multistart_states_single_accepted_root": all(
            bool(r["all_accepted_one_root"]) for r in multistart_summary
        ),
        "physical_domain_rank_deficient_points": sum(
            int(r["rank_deficient_grid_points"]) for r in physical
        ),
        "physical_domain_max_scaled_A_condition": max(
            float(r["A_scaled_condition_max"]) for r in physical
        ),
        "physical_domain_max_J_condition": max(
            float(r["J_condition_max"]) for r in physical
        ),
        "physical_domain_min_J_sigma_min": min(
            float(r["J_sigma_min_min"]) for r in physical
        ),
    }

    summary = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "base_document": str(base_path),
        "base_document_sha256": sha256(base_path),
        "load_disturbed_reference": disturbed_status,
        "representative_states": actual_rows,
        "multistart_summary": multistart_summary,
        "domain_summary": domain_summary,
        "broad_feature_peaks": broad_features,
        "overall": overall,
    }
    write_json(ARTIFACTS / "summary.json", summary, allow_nan=True)

    lines = [
        "# CINDER v1.1.2 closure-conditioning study",
        "",
        "## Physical roots",
        "",
        "| State | λp | λs | scaled κ(A) | κ(J_R) | σmin(J_R) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in actual_rows:
        lines.append(
            f"| {row['label']} | {row['lambda_p']:.5g} | {row['lambda_s']:.5g} | "
            f"{row['A_condition_scaled']:.4g} | {row['J_condition']:.4g} | "
            f"{row['J_sigma_min']:.4g} |"
        )
    lines += [
        "",
        f"- all actual 8×8 closures rank 8: **{overall['all_actual_A_rank_8']}**",
        f"- physical-domain rank-deficient points: **{overall['physical_domain_rank_deficient_points']}**",
        f"- all multi-start state tests found one accepted root cluster: **{overall['all_multistart_states_single_accepted_root']}**",
        f"- worst physical-domain scaled κ(A): `{overall['physical_domain_max_scaled_A_condition']:.6g}`",
        f"- worst physical-domain κ(J_R): `{overall['physical_domain_max_J_condition']:.6g}`",
        f"- minimum physical-domain σmin(J_R): `{overall['physical_domain_min_J_sigma_min']:.6g}`",
        "",
        "Expanded and broad lambda maps are structural diagnostics only. Use the broad feature table and root-slice figures to interpret spikes rather than assigning a cause from condition number alone.",
    ]
    (ARTIFACTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nClosure-conditioning complete: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
