from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
REPO_ROOT = STUDY_ROOT.parents[3]
ARTIFACTS = STUDY_ROOT / "artifacts"
WORK = STUDY_ROOT / "work"
UPSTREAM_ROOT = WORK / "upstream"
MANIFEST_FILE = STUDY_ROOT / "upstream_manifest.json"
STUDY_FILE = STUDY_ROOT / "study.json"
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"

EXPECTED_VERSION = "1.1.2"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=capture,
    )


def verify_release_tag() -> str:
    manifest = load_json(MANIFEST_FILE)
    tag = manifest["release_tag"]
    expected_commit = manifest["release_commit_sha"]
    completed = _git("rev-parse", f"{tag}^{{commit}}")
    actual = completed.stdout.decode("utf-8").strip()
    if actual != expected_commit:
        raise RuntimeError(
            f"{tag} resolves to {actual}, expected {expected_commit}. "
            "The local Git repository does not contain the expected frozen release tag."
        )
    return actual


def materialize_tagged_upstream(*, clean: bool = True) -> Path:
    """Materialize exact launch/result utilities from the frozen release tag.

    This deliberately does not import the working tree's current launchTools.
    The source bytes come from the annotated release tag in the local Git object
    database and are verified by Git blob SHA before they are executed.
    """
    manifest = load_json(MANIFEST_FILE)
    tag = manifest["release_tag"]
    verify_release_tag()

    if clean and UPSTREAM_ROOT.exists():
        shutil.rmtree(UPSTREAM_ROOT)
    UPSTREAM_ROOT.mkdir(parents=True, exist_ok=True)

    for item in manifest["files"]:
        path = item["path"]
        expected = item["git_blob_sha"]
        completed = _git("show", f"{tag}:{path}")
        data = completed.stdout
        actual = git_blob_sha(data)
        if actual != expected:
            raise RuntimeError(
                f"Tagged source blob mismatch for {path}: {actual} != {expected}"
            )
        target = UPSTREAM_ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    return UPSTREAM_ROOT / "cvtModel" / "launchTools"


def verify_environment() -> None:
    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    import cinder

    if cinder.__version__ != EXPECTED_VERSION:
        raise RuntimeError(
            f"Expected cinder-cvt=={EXPECTED_VERSION}, found {cinder.__version__} "
            f"from {Path(cinder.__file__).resolve()}."
        )


def clean_artifacts() -> None:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)


def run_tagged_tool(
    script_name: str,
    arguments: list[str],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    launch_tools = materialize_tagged_upstream(clean=False)
    script = launch_tools / script_name
    if not script.is_file():
        raise FileNotFoundError(script)

    output_dir.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, str(script), "--output-dir", str(output_dir), *arguments]
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"

    print("$ " + " ".join(command))
    subprocess.run(
        command,
        cwd=str(launch_tools),
        check=True,
        env=env,
    )
    return {
        "script": script_name,
        "command": command,
        "output_dir": str(output_dir.resolve()),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _finite(values) -> list[float]:
    out = []
    for value in values:
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def _max_abs(rows: list[dict[str, str]], key: str) -> float | None:
    vals = _finite(row.get(key) for row in rows)
    return max((abs(v) for v in vals), default=None)


def _max_value(rows: list[dict[str, str]], key: str) -> float | None:
    vals = _finite(row.get(key) for row in rows)
    return max(vals, default=None)


def _min_value(rows: list[dict[str, str]], key: str) -> float | None:
    vals = _finite(row.get(key) for row in rows)
    return min(vals, default=None)


def _variant_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        key = row.get("variant")
        if key:
            converted: dict[str, Any] = {}
            for k, v in row.items():
                try:
                    converted[k] = float(v)
                except (TypeError, ValueError):
                    converted[k] = v
            result[key] = converted
    return result


def summarize_canonical_outputs(commands: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_dir = ARTIFACTS / "baseline-ablation"
    coupling_dir = ARTIFACTS / "coupling-energy"

    baseline_summary_rows = _read_csv(baseline_dir / "summary.csv")
    direct_rows = _read_csv(baseline_dir / "direct_clamp_on_full_trajectory.csv")
    mass_rows = _read_csv(baseline_dir / "effective_mass_map.csv")
    coupling_rows = _read_csv(coupling_dir / "coupling_energy_flow.csv")

    baseline_variants = _variant_rows(baseline_summary_rows)

    full_mass = [r for r in mass_rows if r.get("variant") == "full"]
    headline = {
        "primary_max_abs_dynamic_correction_pct_of_qs_total_clamp": _max_abs(
            direct_rows, "primary_dynamic_correction_pct_of_qs_total_clamp"
        ),
        "secondary_max_abs_dynamic_correction_pct_of_qs_total_clamp": _max_abs(
            direct_rows, "secondary_dynamic_correction_pct_of_qs_total_clamp"
        ),
        "primary_max_abs_dynamic_clamp_correction_N": _max_abs(
            direct_rows, "primary_dynamic_correction_to_total_clamp_N"
        ),
        "secondary_max_abs_dynamic_clamp_correction_N": _max_abs(
            direct_rows, "secondary_dynamic_correction_to_total_clamp_N"
        ),
        "full_model_direct_shift_mass_min_kg": _min_value(
            full_mass, "mass_total_direct_kg"
        ),
        "full_model_direct_shift_mass_max_kg": _max_value(
            full_mass, "mass_total_direct_kg"
        ),
        "flyweight_reflected_shift_mass_max_kg": _max_value(
            full_mass, "mass_flyweight_active_kg"
        ),
        "helix_reflected_shift_mass_max_kg": _max_value(
            full_mass, "mass_helix_active_kg"
        ),
        "flyweight_pivot_energy_max_J": _max_value(
            coupling_rows, "flyweight_pivot_energy_J"
        ),
        "flyweight_config_power_max_abs_W": _max_abs(
            coupling_rows, "flyweight_config_power_to_axial_W"
        ),
        "helix_cross_energy_max_abs_J": _max_abs(
            coupling_rows, "secondary_helix_cross_energy_J"
        ),
        "helix_relative_energy_max_J": _max_value(
            coupling_rows, "secondary_helix_relative_energy_J"
        ),
        "helix_reflected_shift_mass_trace_max_kg": _max_value(
            coupling_rows, "helix_reflected_shift_mass_kg"
        ),
    }

    payload = {
        "study": load_json(STUDY_FILE),
        "release": {
            "tag_commit": verify_release_tag(),
            "upstream_manifest": load_json(MANIFEST_FILE),
        },
        "commands": commands,
        "canonical": {
            "baseline_variants": baseline_variants,
            "headline": headline,
        },
        "exploration_status": (
            "Existing stress-search and helix-scaling machinery is retained only as "
            "exploratory infrastructure. Do not freeze off-baseline threshold claims "
            "until the experiments are redesigned around explicit physical scales."
        ),
    }
    return payload


def _fmt(value: Any, digits: int = 5) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "n/a"
        return f"{value:.{digits}g}"
    return str(value)


def write_summary(payload: dict[str, Any]) -> None:
    (ARTIFACTS / "summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    h = payload["canonical"]["headline"]
    variants = payload["canonical"]["baseline_variants"]

    lines = [
        "# CINDER 1.1.2 actuator-dynamics study — run summary",
        "",
        "## Status",
        "",
        "Canonical results in this study are the baseline four-model ablation and the "
        "coupling-energy/generalized-inertia decomposition. Off-baseline search/sweep "
        "outputs remain exploratory.",
        "",
        "## Same-state dynamic actuator corrections",
        "",
        f"- max |primary dynamic correction / QS total primary clamp|: "
        f"`{_fmt(h['primary_max_abs_dynamic_correction_pct_of_qs_total_clamp'])}%`",
        f"- max |secondary dynamic correction / QS total secondary clamp|: "
        f"`{_fmt(h['secondary_max_abs_dynamic_correction_pct_of_qs_total_clamp'])}%`",
        f"- max |primary dynamic clamp correction|: "
        f"`{_fmt(h['primary_max_abs_dynamic_clamp_correction_N'])} N`",
        f"- max |secondary dynamic clamp correction|: "
        f"`{_fmt(h['secondary_max_abs_dynamic_clamp_correction_N'])} N`",
        "",
        "## Generalized shift-inertia / energy diagnostics",
        "",
        f"- full-model direct generalized shift mass range: "
        f"`{_fmt(h['full_model_direct_shift_mass_min_kg'])}` to "
        f"`{_fmt(h['full_model_direct_shift_mass_max_kg'])} kg`",
        f"- max flyweight reflected shift-mass contribution: "
        f"`{_fmt(h['flyweight_reflected_shift_mass_max_kg'])} kg`",
        f"- max helix reflected shift-mass contribution: "
        f"`{_fmt(h['helix_reflected_shift_mass_max_kg'])} kg`",
        f"- max flyweight pivot kinetic energy: "
        f"`{_fmt(h['flyweight_pivot_energy_max_J'])} J`",
        f"- max |flyweight configuration power to axial DOF|: "
        f"`{_fmt(h['flyweight_config_power_max_abs_W'])} W`",
        f"- max |secondary helix kinetic cross term|: "
        f"`{_fmt(h['helix_cross_energy_max_abs_J'])} J`",
        f"- max secondary helix relative-rotation kinetic energy: "
        f"`{_fmt(h['helix_relative_energy_max_J'])} J`",
        "",
        "## Independently integrated variants",
        "",
    ]
    for key in (
        "full",
        "quasi_static_flyweight",
        "quasi_static_helix",
        "fully_quasi_static",
    ):
        row = variants.get(key)
        if not row:
            continue
        lines.append(
            f"- **{row.get('variant_label', key)}**: "
            f"time-to-full-shift `{_fmt(row.get('time_to_full_shift_s'))} s`; "
            f"transitions `{_fmt(row.get('hybrid_transition_count'), 0)}`; "
            f"mean primary clamp `{_fmt(row.get('primary_clamp_mean_N'))} N`; "
            f"mean secondary clamp `{_fmt(row.get('secondary_clamp_mean_N'))} N`."
        )

    lines += [
        "",
        "## Interpretation boundary",
        "",
        "This file is intentionally descriptive. It does not freeze a claim that the "
        "current exploratory stress-search or helix inertia/torque threshold sweep is "
        "the final off-baseline result. Those experiments are retained to guide the "
        "next equation-led study design.",
        "",
    ]
    (ARTIFACTS / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def copy_provenance() -> None:
    destination = ARTIFACTS / "provenance"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STUDY_FILE, destination / "study.json")
    shutil.copy2(MANIFEST_FILE, destination / "upstream_manifest.json")
