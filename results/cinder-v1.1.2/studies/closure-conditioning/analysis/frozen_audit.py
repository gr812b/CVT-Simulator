"""Selected frozen-state checks, not a new transient or operating-domain search.

Recover the archived kinematics literally. The archived one-sided helix guard
is checked as well as the current bilateral reference; the signed balances
are identical. No legacy exploration imports or live simulator source are used.
"""
from __future__ import annotations

from types import SimpleNamespace
import math
import numpy as np
from scipy.optimize import root, minimize_scalar

from cinder.contracts import decode_simulation_case_document
from cinder.execution.hybrid.cvt_regime import CVTShiftConstraint
from cinder.model.cvt.contact import ContactInterface, ContactTractionUtilization
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system import CVTState
from infrastructure.case_library import make_bench_system, full_state
from defaults.reference_model import decode_reference_case
from .evidence import RELEASE, read_json, rows, write_json, write_rows


def utilization(lp, ls):
    return ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls))


class FrozenFamily:
    def __init__(self, cc, recipe, library, tp, ts, *, bilateral=False):
        self.cc, self.recipe, self.library = cc, recipe, library
        self.tp, self.ts = float(tp), float(ts)
        document = read_json(RELEASE / "defaults/baja/simulation_case.json")
        self.decoded = (decode_reference_case if bilateral else decode_simulation_case_document)(document)
        self.base = self.bundle(ts)
        self.basis = self.bundle(ts + 1.0)

    def bundle(self, ts):
        system = make_bench_system(self.decoded, self.library, primary_torque=self.tp, secondary_torque=float(ts))
        spec = system.cvt.model.geometry.spec
        r = self.recipe
        s = spec.deadzone_shift + float(r["shift_fraction"]) * (spec.max_shift - spec.deadzone_shift)
        cvt = CVTState(float(r["resolved_primary_rpm"]) * math.pi / 30,
                       float(r["resolved_secondary_rpm"]) * math.pi / 30,
                       float(r["resolved_belt_speed_m_s"]), s, float(r["shift_speed_mm_s"]) / 1000)
        state = full_state(system, cvt)
        snapshot = system.cvt.model.snapshot_at_time(time=0., state=cvt,
            shaft_boundaries=system._shaft_boundaries(time=0., state=state), geometry_side="engaged")
        closure = EngagedContactClosure(snapshot=snapshot, shift_constraint=EngagedShiftConstraint.FREE)
        ref = SimpleNamespace(decoded=SimpleNamespace(system=system))
        sample = SimpleNamespace(time=0., composed_mode=SimpleNamespace(cvt=SimpleNamespace(shift_constraint=CVTShiftConstraint.FREE)))
        return SimpleNamespace(system=system, cvt=cvt, snapshot=snapshot, closure=closure, ref=ref, sample=sample)

    @staticmethod
    def at(bundle, lp, ls, *, diagnostics=False):
        return bundle.closure.evaluate_trial(traction_utilization=utilization(lp, ls),
            maximum_closure_condition_number=None, capture_diagnostics=diagnostics)

    @staticmethod
    def residual_trial(trial):
        return np.array([trial.relative_motion.primary_relative_acceleration,
                         trial.relative_motion.secondary_relative_acceleration])

    def residual(self, lp, ls, ts=None):
        a = self.residual_trial(self.at(self.base, lp, ls))
        if ts is None or ts == self.ts:
            return a
        b = self.residual_trial(self.at(self.basis, lp, ls))
        return a + (float(ts) - self.ts) * (b - a)

    def jacobian(self, lp, ls, ts=None, h=1e-5):
        return np.column_stack(((self.residual(lp+h, ls, ts)-self.residual(lp-h, ls, ts))/(2*h),
                                (self.residual(lp, ls+h, ts)-self.residual(lp, ls-h, ts))/(2*h)))

    def diagnose(self, lp, ls, ts=None):
        ts = self.ts if ts is None else float(ts)
        b = self.bundle(ts)
        trial = self.at(b, lp, ls, diagnostics=True)
        code, extra = self.cc.topology_failure_code(b.ref, b.sample, trial, utilization(lp, ls), b.snapshot)
        a, u, law = trial.closure, trial.closure.unknowns, b.system.cvt.traction_law
        J = self.jacobian(lp, ls, ts)
        sv = np.linalg.svd(J, compute_uv=False)
        row = dict(lambda_p=float(lp), lambda_s=float(ls), primary_boundary_torque_Nm=self.tp,
            secondary_boundary_torque_Nm=ts, R_p=float(trial.relative_motion.primary_relative_acceleration),
            R_s=float(trial.relative_motion.secondary_relative_acceleration),
            primary_relative_speed_m_s=float(trial.relative_motion.primary_relative_speed),
            secondary_relative_speed_m_s=float(trial.relative_motion.secondary_relative_speed),
            N_p_N=float(u.primary_normal_resultant), N_s_N=float(u.secondary_normal_resultant),
            tau_p_Nm=float(u.primary_torque), tau_s_Nm=float(u.secondary_torque),
            alpha_p_rad_s2=float(u.primary_angular_acceleration), alpha_s_rad_s2=float(u.secondary_angular_acceleration),
            belt_acceleration_m_s2=float(u.belt_acceleration), shift_acceleration_m_s2=float(u.shift_acceleration),
            min_tension_N=extra["min_belt_tension"], min_local_normal_p_N_per_rad=extra["min_local_normal_p"],
            min_local_normal_s_N_per_rad=extra["min_local_normal_s"], mechanism_margin=extra["mechanism_margin"],
            topology_failure_code=int(code), A_rank=int(a.matrix_rank), A_condition_scaled=float(a.scaled_condition_number),
            A_max_equation_residual=float(a.max_abs_equation_residual), J_condition=float(sv[0]/sv[-1]),
            J_sigma_min=float(sv[-1]), J_determinant=float(np.linalg.det(J)),
            static_margin_p=float(law.static_margin_at(ContactInterface.PRIMARY, lp)),
            static_margin_s=float(law.static_margin_at(ContactInterface.SECONDARY, ls)))
        row["physical"] = code == 0 and min(row["static_margin_p"], row["static_margin_s"]) >= 0.
        return row


def run_frozen_audit(cc, artifacts):
    library = read_json(artifacts / "full/summary.json")["shared_case_library"]
    c = rows(artifacts / "two_contact/candidate.csv")[0]
    tp, ts = c["refined_Tp_Nm"], c["refined_Ts_Nm"]
    f = FrozenFamily(cc, c, library, tp, ts)
    bilateral = FrozenFamily(cc, c, library, tp, ts, bilateral=True)
    root_rows, jac_rows = [], []
    for i in (1, 2):
        lp, ls = c[f"root{i}_lambda_p"], c[f"root{i}_lambda_s"]
        d = f.diagnose(lp, ls)
        if np.hypot(d["R_p"], d["R_s"]) > 1e-6 or not d["physical"] or d["A_rank"] != 8:
            raise ValueError(f"Archived selected root {i} failed the fresh frozen check: {d}")
        d["root_id"] = i
        bi = bilateral.diagnose(lp, ls)
        d["bilateral_physical"] = bi["physical"]
        d["bilateral_response_max_abs_difference"] = max(abs(d[k]-bi[k]) for k in
            ("N_p_N", "N_s_N", "alpha_p_rad_s2", "alpha_s_rad_s2", "belt_acceleration_m_s2", "shift_acceleration_m_s2"))
        if not bi["physical"] or d["bilateral_response_max_abs_difference"] > 1e-9:
            raise ValueError("Selected legacy response differs under the current bilateral reference.")
        root_rows.append(d)
        for h in (1e-3, 3e-4, 1e-4, 3e-5, 1e-5, 3e-6, 1e-6):
            J = f.jacobian(lp, ls, h=h)
            jac_rows.append(dict(root_id=i, step=h, J00=J[0,0], J01=J[0,1], J10=J[1,0], J11=J[1,1],
                                 condition=float(np.linalg.cond(J)), determinant=float(np.linalg.det(J))))
    out = artifacts / "selected_audit"
    write_rows(out / "two_contact_roots.csv", root_rows)
    write_rows(out / "root_jacobian_steps.csv", jac_rows)

    # Correct the retained inverse-grid curve locally. lambda_s is a traction
    # coordinate (not time or shift), and is monotone on this selected segment.
    old_curve = rows(artifacts / "two_contact/fixed_other_torque_solution_curve.csv")
    old_curve = sorted(old_curve, key=lambda r: r["lambda_s"])
    def on_curve(ls):
        guess = min(old_curve, key=lambda r: abs(r["lambda_s"]-ls))
        sol = root(lambda z: f.residual(z[0], ls, z[1]), [guess["lambda_p"], guess["continued_torque_Nm"]], tol=1e-10)
        lp, tq = sol.x
        if np.linalg.norm(f.residual(lp, ls, tq)) > 1e-6 or abs(lp-guess["lambda_p"]) > .025:
            raise ValueError("Local fixed-primary-torque correction left the retained branch.")
        return float(lp), float(tq)
    fold = minimize_scalar(lambda ls: -on_curve(ls)[1], bounds=(root_rows[0]["lambda_s"], root_rows[1]["lambda_s"]),
                           method="bounded", options={"xatol":1e-11})
    if not fold.success:
        raise ValueError("Local torque-extremum refinement failed.")
    fold_ls = float(fold.x)
    curve_rows = []
    for ls in sorted(set(np.linspace(.30, .59, 181).tolist()+[r["lambda_s"] for r in root_rows]+[fold_ls])):
        lp, tq = on_curve(ls)
        d = f.diagnose(lp, ls, tq)
        d["direct_vs_affine_residual_max"] = float(np.max(np.abs(f.residual(lp, ls, tq)-np.array([d["R_p"], d["R_s"]]))))
        if max(abs(d["R_p"]), abs(d["R_s"])) > 1e-6:
            raise ValueError("Corrected curve fails direct CINDER evaluation.")
        curve_rows.append(d)
    write_rows(out / "fixed_primary_curve.csv", curve_rows)

    # A focused residual map resolves the two simultaneous zeros at publication
    # scale; no new operating point is searched and no time integration occurs.
    lp = np.linspace(-.310, -.258, 121)
    ls = np.linspace(.30, .59, 161)
    rp, rs = np.zeros((len(ls), len(lp))), np.zeros((len(ls), len(lp)))
    for i, y in enumerate(ls):
        for j, x in enumerate(lp):
            rp[i,j], rs[i,j] = f.residual(x, y)
    np.savez_compressed(out / "focused_residual_map.npz", lambda_p=lp, lambda_s=ls, R_p=rp, R_s=rs)

    m = read_json(artifacts / "one_contact/best/best_candidate.json")
    mixed = FrozenFamily(cc, m, library, m["fixed_torque_Nm"], m["two_root_varied_torque_Nm"])
    mixed_bilateral = FrozenFamily(cc, m, library, m["fixed_torque_Nm"], m["two_root_varied_torque_Nm"], bilateral=True)
    kinetic = mixed.base.system.cvt.traction_law
    if m["kinetic_lambda"] != -float(kinetic.primary_kinetic_lambda_magnitude):
        raise ValueError("Selected primary traction is not the prescribed negative kinetic value.")
    mixed_rows = []
    for i in (1, 2):
        d = mixed.diagnose(m["kinetic_lambda"], m[f"root{i}_lambda"])
        d["root_id"] = i
        # Only R_s is constrained here. The scalar slope, not a 2x2 condition
        # number for an unconstrained primary residual, characterizes this root.
        d["dR_s_dlambda_s_m_s2"] = float(mixed.jacobian(d["lambda_p"], d["lambda_s"])[1,1])
        bi = mixed_bilateral.diagnose(d["lambda_p"], d["lambda_s"])
        d["bilateral_physical"] = bi["physical"]
        d["bilateral_response_max_abs_difference"] = max(abs(d[k]-bi[k]) for k in
            ("N_p_N", "N_s_N", "alpha_p_rad_s2", "alpha_s_rad_s2", "belt_acceleration_m_s2", "shift_acceleration_m_s2"))
        # At the retained zero-speed onset lambda_p=-mu_k requires positive
        # primary relative acceleration. No permissive exception fallback.
        d["slip_direction_consistent"] = abs(d["primary_relative_speed_m_s"]) < 1e-8 and d["R_p"] > 0
        if (abs(d["R_s"]) > 1e-6 or not d["physical"] or not d["slip_direction_consistent"]
                or not bi["physical"] or d["bilateral_response_max_abs_difference"] > 1e-9):
            raise ValueError(f"Selected scalar root fails mechanics/onset-direction check: {d}")
        mixed_rows.append(d)
    write_rows(out / "one_contact_roots.csv", mixed_rows)
    fd = min(curve_rows, key=lambda r: abs(r["lambda_s"]-fold_ls))
    write_json(out / "summary.json", {
        "state_id": c["state_id"], "kinematics": {k:c[k] for k in ("shift_fraction", "shift_speed_mm_s", "resolved_primary_rpm", "resolved_secondary_rpm", "resolved_belt_speed_m_s")},
        "boundary_inertia_kg_m2": [library["fixed_boundary_bench"]["primary_inertia_kg_m2"], library["fixed_boundary_bench"]["secondary_inertia_kg_m2"]],
        "fixed_primary_torque_Nm": tp, "selected_secondary_torque_Nm": ts,
        "fold": fd, "curve_points": len(curve_rows),
        "continuation_coordinate": "secondary traction utilization lambda_s; frozen position and velocities; no time evolution",
        "historical_guard": "Original cinder-cvt 1.1.2 one-sided helix contact checked; selected two-contact and one-contact roots additionally pass current bilateral reference with identical response.",
        "new_work": "Only selected frozen roots, central derivatives, local curve correction and focused residual grid; retained full maps and censuses are not rerun.",
    })
