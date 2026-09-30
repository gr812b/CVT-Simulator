"""Rebuild every current CINDER Results/appendix figure from accepted retained evidence.

This command is deliberately figure-only.  It never calls a study ``run.py``
that can integrate a trajectory, never chooses the newest run, and never writes
to the manuscript figure directory.  Candidate assets are written to a fresh
output directory and each family is isolated so one failure does not hide the
status of the others.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parents[2]
REPO = HERE.parents[1]
BASELINE_HEAD = "953d1b0423d0655002271de2af43a72c47cff87e"
MECHANICS_COMMIT = "7637a38b4fb9ec21dfb953c1c80a27ec5f389654"
ALL_RUN_ID = "20260929T124106516965Z"
BALLEW_RUN_ID = "20260929T165922834300Z"
PREP_RUN_ID = "prep_20260929T205331850596Z"
COURSE_NPZ_SHA256 = "990c70ea87f3a42f0e941952a2f700abf479a5a0909f5c2505f2f6daff571266"

EXPECTED_ASSETS = (
    "verification/energy_balance.pdf",
    "verification/gross_motion_hybrid_history.pdf",
    "verification/solver_refinement.pdf",
    "verification/closure_robustness.pdf",
    "verification/sticking_closure_fold.pdf",
    "ballew/protocol_comparison.pdf",
    "ballew/internal_response.pdf",
    "dynamics/primary_engagement.pdf",
    "dynamics/primary_torque_ramps.pdf",
    "dynamics/secondary_launch.pdf",
    "dynamics/secondary_backshift.pdf",
    "dynamics/secondary_continuous_response.pdf",
    "dynamics/belt_load_rate.pdf",
    "course/common_course_profile.png",
    "course/opening_free_shift_characteristics.png",
    "course/shift_curve_mechanical_causes.png",
    "course/severe_hill_response.png",
    "course/d02_traction_power.png",
    "course/d02_hill_repairs.png",
    "course/cyclic_shift_and_support.png",
    "course/moderate_hill_operating_conditions.png",
    "course/descent_reverse_power.png",
    "verification/solver_acceptance_support.pdf",
    "verification/solver_population_support.pdf",
    "dynamics/secondary_support.pdf",
    "dynamics/belt_shift_transient.pdf",
    "dynamics/belt_coefficient_driver.pdf",
    "dynamics/belt_density_response.pdf",
)

FAMILY_ASSETS = {
    "energy": ("verification/energy_balance.pdf",),
    "solver": (
        "verification/gross_motion_hybrid_history.pdf",
        "verification/solver_refinement.pdf",
        "verification/solver_acceptance_support.pdf",
        "verification/solver_population_support.pdf",
    ),
    "closure": ("verification/closure_robustness.pdf", "verification/sticking_closure_fold.pdf"),
    "ballew": ("ballew/protocol_comparison.pdf", "ballew/internal_response.pdf"),
    "primary": ("dynamics/primary_engagement.pdf", "dynamics/primary_torque_ramps.pdf"),
    "secondary": (
        "dynamics/secondary_launch.pdf", "dynamics/secondary_backshift.pdf",
        "dynamics/secondary_continuous_response.pdf", "dynamics/secondary_support.pdf",
    ),
    "belt": (
        "dynamics/belt_load_rate.pdf", "dynamics/belt_shift_transient.pdf",
        "dynamics/belt_coefficient_driver.pdf", "dynamics/belt_density_response.pdf",
    ),
    "course": tuple(x for x in EXPECTED_ASSETS if x.startswith("course/")),
}


class MissingInput(RuntimeError):
    pass


class Blocked(RuntimeError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def has_nonfinite_json(value):
    """True when a parsed JSON-like structure contains NaN or infinity.

    Historical exporter JSON may use Python's permissive NaN tokens. The final
    handoff remains strict JSON: such source content is referenced by hash/size
    rather than silently coercing its scientific values.
    """
    if isinstance(value, float):
        return not __import__("math").isfinite(value)
    if isinstance(value, dict):
        return any(has_nonfinite_json(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_nonfinite_json(v) for v in value)
    return False


def run_capture(cmd, *, cwd=None, log=None):
    proc = subprocess.run([str(x) for x in cmd], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log is not None:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(proc.stdout, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"exit {proc.returncode}: {' '.join(map(str, cmd))}")
    return proc.stdout


def git_output(*args):
    return subprocess.run(["git", *args], cwd=REPO, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()


def run_context_identity(root: Path, expected_id: str):
    p = root / "run_context.json"
    if not p.is_file():
        raise MissingInput(f"missing run_context.json: {p}")
    d = load_json(p)
    started = d.get("started_utc") or Path(str(d.get("output", ""))).name
    output_name = Path(str(d.get("output", ""))).name
    if expected_id not in {started, output_name, root.name}:
        raise ValueError(f"run identity mismatch for {root}: expected {expected_id}, got {started!r}/{output_name!r}")
    if d.get("mechanics_commit") and d["mechanics_commit"] != MECHANICS_COMMIT:
        raise ValueError(f"mechanics commit mismatch in {p}")
    return d


def find_step(report: dict, step_id: str):
    return next((x for x in report.get("steps", []) if x.get("id") == step_id), None)


def require_historical_pass(report_path: Path, ids):
    if not report_path.is_file():
        raise MissingInput(f"missing historical health report: {report_path}")
    report = load_json(report_path)
    bad = []
    for step_id in ids:
        row = find_step(report, step_id)
        if not row or row.get("status") != "PASS":
            bad.append((step_id, None if row is None else row.get("status")))
    if bad:
        raise ValueError(f"required historical checks are not PASS in {report_path}: {bad}")
    return {step_id: "PASS" for step_id in ids}


def manuscript_results_imports(tex_path: Path):
    if not tex_path.is_file():
        raise MissingInput(f"missing manuscript TeX: {tex_path}")
    text = tex_path.read_text(encoding="utf-8")
    matches = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*figures/results/[^}]*)\}", text)
    prefix = "figures/results/"
    imports = []
    for value in matches:
        value = value.replace("\\", "/")
        if prefix not in value:
            continue
        imports.append(value.split(prefix, 1)[1])
    return tuple(dict.fromkeys(imports))


def no_write_preflight(args):
    all_run = args.all_run.resolve(); ballew = args.ballew_run.resolve(); prep = args.prep_run.resolve()
    solver = args.solver_retained.resolve(); closure = args.closure_retained.resolve()
    result = {"status": "PASS", "checks": {}, "warnings": []}

    try:
        head = git_output("rev-parse", "HEAD")
        result["checks"]["git_head"] = head
        result["checks"]["baseline_head"] = BASELINE_HEAD
        try:
            git_output("merge-base", "--is-ancestor", BASELINE_HEAD, head)
            result["checks"]["baseline_is_ancestor"] = True
        except Exception:
            result["checks"]["baseline_is_ancestor"] = False
            raise ValueError(f"Reviewed figure baseline {BASELINE_HEAD} is not an ancestor of HEAD {head}")
        result["checks"]["git_status_porcelain"] = git_output("status", "--porcelain")
    except Exception as e:
        result["status"] = "FAIL"; result["checks"]["git"] = repr(e)

    tex = REPO / "docs/CVT_Module_Formulation/CVT_Module_Formulation.tex"
    try:
        imports = manuscript_results_imports(tex)
        result["checks"]["manuscript_results_imports"] = list(imports)
        result["checks"]["manuscript_results_import_count"] = len(imports)
        if set(imports) != set(EXPECTED_ASSETS) or len(imports) != len(EXPECTED_ASSETS):
            missing = sorted(set(EXPECTED_ASSETS) - set(imports))
            extra = sorted(set(imports) - set(EXPECTED_ASSETS))
            raise ValueError(f"current TeX Results/appendix figure inventory changed; missing={missing}, extra={extra}")
    except Exception as e:
        result["status"] = "FAIL"; result["checks"]["manuscript_inventory_error"] = repr(e)

    required = [
        all_run / "data/energy",
        all_run / "data/belt",
        ballew / "prepared/ballew",
        prep / "prepared/actuator",
        prep / "prepared/belt",
        prep / "prepared/course/course_plot_inputs.npz",
        solver / "evidence/artifacts",
        solver / "check_package.py",
        closure / "evidence/reviewed",
        closure / "check_package.py",
        HERE / "results_health/figure_only_worker.py",
        HERE / "studies/course-tuning/analysis/course_publication_export.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    result["checks"]["required_inputs_missing"] = missing
    if missing:
        result["status"] = "FAIL"

    for root, ident in ((all_run, ALL_RUN_ID), (ballew, BALLEW_RUN_ID), (prep, PREP_RUN_ID)):
        try:
            result["checks"][f"run_{ident}"] = run_context_identity(root, ident)
        except Exception as e:
            result["status"] = "FAIL"; result["checks"][f"run_{ident}"] = repr(e)

    npz = prep / "prepared/course/course_plot_inputs.npz"
    if npz.is_file():
        actual = sha(npz); result["checks"]["course_plot_inputs_sha256"] = actual
        if actual != COURSE_NPZ_SHA256:
            result["status"] = "FAIL"

    belt_source = HERE / "results_health/belt.py"
    if belt_source.is_file():
        text = belt_source.read_text(encoding="utf-8")
        fixed = "for name, expected_hash in portable_hashes(provenance['raw_sha256']).items():" in text
        result["checks"]["belt_count_shadow_fix_present"] = fixed
        if not fixed:
            result["status"] = "FAIL"
    else:
        result["status"] = "FAIL"; result["checks"]["belt_count_shadow_fix_present"] = False

    verify = HERE / "verify_environment.py"
    if verify.is_file():
        proc = subprocess.run([sys.executable, str(verify)], cwd=HERE, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        result["checks"]["verify_environment"] = {"exit_code": proc.returncode, "output": proc.stdout}
        if proc.returncode:
            result["status"] = "FAIL"
    else:
        result["status"] = "FAIL"; result["checks"]["verify_environment"] = "missing"
    return result


def png_check(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            dims = list(im.size)
        return {"ok": dims[0] > 10 and dims[1] > 10, "dimensions_px": dims}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def pdf_check(path: Path):
    b = path.read_bytes()
    eof = b.rstrip().endswith(b"%%EOF")
    header = b.startswith(b"%PDF-")
    image_xobjects = b.count(b"/Subtype /Image")
    fonts = b.count(b"/Font")
    # A Matplotlib PDF may selectively rasterize a dense artist, but a PNG
    # merely wrapped as a PDF usually has image content and no font resources.
    not_plain_wrapper = not (image_xobjects > 0 and fonts == 0)
    return {"ok": bool(header and eof and not_plain_wrapper), "pdf_header": header,
            "eof": eof, "image_xobjects": image_xobjects,
            "font_resource_mentions": fonts, "not_plain_png_wrapper": not_plain_wrapper}


def image_compare(candidate: Path, reference: Path):
    if not reference.is_file():
        return {"status": "MISSING_REFERENCE"}
    try:
        from PIL import Image, ImageChops, ImageStat
        with Image.open(candidate).convert("RGB") as a, Image.open(reference).convert("RGB") as b:
            result = {"candidate_dimensions": list(a.size), "reference_dimensions": list(b.size)}
            if a.size != b.size:
                delta=[int(a.size[0]-b.size[0]), int(a.size[1]-b.size[1])]
                result["dimension_delta_px"] = delta
                result["status"] = "DIMENSION_NEAR_MATCH" if max(abs(x) for x in delta) <= 6 else "DIMENSION_DIFFERENCE"
                return result
            diff = ImageChops.difference(a, b)
            stat = ImageStat.Stat(diff)
            result["mean_abs_channel"] = sum(stat.mean) / 3.0
            result["mean_abs_fraction_255"] = result["mean_abs_channel"] / 255.0
            result["status"] = "BYTE_IDENTICAL" if sha(candidate) == sha(reference) else "PIXEL_COMPARED"
            return result
    except Exception as e:
        return {"status": "COMPARE_ERROR", "error": repr(e)}


def write_html_report(path: Path, report: dict):
    rows = []
    for s in report["steps"]:
        rows.append(f"<tr><td>{html.escape(s['id'])}</td><td>{html.escape(s['status'])}</td><td>{html.escape(s.get('detail',''))}</td></tr>")
    asset_rows = []
    for name, meta in report.get("assets", {}).items():
        asset_rows.append(f"<tr><td>{html.escape(name)}</td><td>{meta.get('bytes','')}</td><td><code>{meta.get('sha256','')}</code></td><td>{html.escape(str(meta.get('render_check',{}).get('ok','')))}</td></tr>")
    body = f"""<!doctype html><meta charset='utf-8'><title>CINDER figure-only health</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{border:1px solid #ccc;padding:.35rem;vertical-align:top}}code{{font-size:.8rem;word-break:break-all}}</style>
<h1>CINDER v1.1.2 figure-only health</h1>
<p><b>Ready to freeze:</b> {str(report.get('ready_to_freeze')).lower()}</p>
<p>Numerical execution identities remain separate from this export run identity.</p>
<h2>Steps</h2><table><tr><th>Step</th><th>Status</th><th>Detail</th></tr>{''.join(rows)}</table>
<h2>Final assets</h2><table><tr><th>Asset</th><th>Bytes</th><th>SHA-256</th><th>Render check</th></tr>{''.join(asset_rows)}</table>
<h2>Limitations</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in report.get('limitations',[]))}</ul>"""
    path.write_text(body, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all-run", type=Path, default=HERE / "health_runs" / ALL_RUN_ID)
    p.add_argument("--ballew-run", type=Path, default=HERE / "health_runs" / BALLEW_RUN_ID)
    p.add_argument("--prep-run", type=Path, default=HERE / "health_runs" / PREP_RUN_ID)
    p.add_argument("--solver-retained", type=Path, default=HERE / "retained_evidence" / "CINDER_4_2_3_Rebuilt_2026-09-25")
    p.add_argument("--closure-retained", type=Path, default=HERE / "retained_evidence" / "CINDER_4_2_4_Rebuilt_2026-09-25")
    p.add_argument("--output-dir", type=Path, default=HERE / "figure_runs" / "final_candidate_20260930")
    p.add_argument("--preflight-only", action="store_true", help="Perform read-only checks and exit without creating files.")
    args = p.parse_args()

    preflight = no_write_preflight(args)
    if args.preflight_only:
        print(json.dumps(preflight, indent=2))
        return 0 if preflight["status"] == "PASS" else 2
    if preflight["status"] != "PASS":
        print(json.dumps(preflight, indent=2))
        print("Preflight failed; no output directory was created.", file=sys.stderr)
        return 2

    out = args.output_dir.resolve()
    if out.exists():
        raise SystemExit(f"Refusing to reuse output directory: {out}")
    figures = out / "figures/results"; logs = out / "logs"; checks = out / "checks"; staging = out / "staging"; support = out / "support"
    for d in (figures, logs, checks, staging, support): d.mkdir(parents=True, exist_ok=False if d == figures else True)

    started = time.time(); steps = []; companions = {}
    def step(step_id, fn, *, blocked_by=()):
        blocked = [x for x in blocked_by if next((r for r in steps if r["id"] == x and r["status"] != "PASS"), None)]
        if blocked:
            row={"id":step_id,"status":"BLOCKED","detail":"blocked by: "+", ".join(blocked),"elapsed_s":0.0};steps.append(row);return None
        t=time.time()
        try:
            value=fn(); row={"id":step_id,"status":"PASS","detail":"","elapsed_s":round(time.time()-t,3)}
            if isinstance(value,dict): row["result"]=value
        except MissingInput as e: row={"id":step_id,"status":"MISSING","detail":str(e),"elapsed_s":round(time.time()-t,3)}; value=None
        except Blocked as e: row={"id":step_id,"status":"BLOCKED","detail":str(e),"elapsed_s":round(time.time()-t,3)}; value=None
        except Exception as e:
            row={"id":step_id,"status":"FAIL","detail":repr(e),"traceback":traceback.format_exc(),"elapsed_s":round(time.time()-t,3)}; value=None
        steps.append(row); print(f"[{row['status']}] {step_id} {row['detail']}"); return value

    all_run=args.all_run.resolve(); ballew=args.ballew_run.resolve(); prep=args.prep_run.resolve(); solver=args.solver_retained.resolve(); closure=args.closure_retained.resolve()

    step("historical-prep-health", lambda: require_historical_pass(prep/"health_report.json", ["primary-health","secondary-health","belt-health","course-health","primary-prepare","secondary-prepare","belt-prepare","course-prepare","ballew-register-accepted-run"]))
    step("historical-ballew-health", lambda: require_historical_pass(ballew/"health_report.json", ["ballew-inputs","ballew-replay","ballew-nominal","ballew-half-step","ballew-quarter-step","ballew-tight","ballew-collect","ballew-prepare","ballew-health","ballew-figures"]))

    def retained_check(root, label):
        log=logs/f"{label}_check_package.log"; run_capture([sys.executable, root/"check_package.py"],cwd=root,log=log); return {"root":str(root),"check_package_sha256":sha(root/"check_package.py")}
    step("solver-retained-integrity", lambda: retained_check(solver,"solver"))
    step("closure-retained-integrity", lambda: retained_check(closure,"closure"))

    def refresh_belt():
        # Read-only check on accepted evidence; write only the new health record.
        while str(HERE) in sys.path: sys.path.remove(str(HERE))
        sys.path.insert(0,str(HERE))
        mod=importlib.import_module("results_health.belt")
        result=mod.check_publication(prep/"prepared/belt", all_run/"data/belt", HERE/"studies/reduced-belt-transients/publication_inputs/runtime_source_check.json")
        if result.get("run_count") != 42: raise ValueError(f"expected 42 reduced-belt runs, got {result.get('run_count')}")
        write_json(checks/"belt-health-refresh.json",{"status":"PASS","result":result})
        return result
    step("belt-health-refresh", refresh_belt, blocked_by=("historical-prep-health",))

    worker=HERE/"results_health/figure_only_worker.py"
    def worker_family(family,input_dir,stage):
        log=logs/f"export_{family}.log"; run_capture([sys.executable,worker,"--family",family,"--input-dir",input_dir,"--output-dir",stage],cwd=HERE,log=log)
        return {"input":str(input_dir),"output":str(stage)}

    step("export-energy", lambda: worker_family("energy",all_run/"data/energy",staging/"energy"))
    step("export-solver", lambda: worker_family("solver",solver/"evidence/artifacts",staging/"solver"), blocked_by=("solver-retained-integrity",))
    step("export-closure", lambda: worker_family("closure",closure/"evidence/reviewed",staging/"closure"), blocked_by=("closure-retained-integrity",))

    def run_plot_script(name, script, input_dir, stage, extra=()):
        if not script.is_file(): raise MissingInput(str(script))
        cmd=[sys.executable,script,"--input-dir",input_dir]
        # Study scripts use different output option names.
        if name in {"primary","secondary"}: cmd += ["--figure-dir",stage]
        elif name == "ballew": cmd += ["--output-dir",stage,"--figure","all"]
        else: raise AssertionError(name)
        cmd += list(extra)
        run_capture(cmd,cwd=script.parents[1],log=logs/f"export_{name}.log")
        return {"script_sha256":sha(script),"input":str(input_dir)}

    step("export-ballew", lambda: run_plot_script("ballew",HERE/"studies/ballew-2015/analysis/publication_plots.py",ballew/"prepared/ballew",staging/"ballew"), blocked_by=("historical-ballew-health",))
    step("export-primary", lambda: run_plot_script("primary",HERE/"studies/actuator-dynamics/analysis/primary_publication_plots.py",prep/"prepared/actuator",staging/"primary"), blocked_by=("historical-prep-health",))
    step("export-secondary", lambda: run_plot_script("secondary",HERE/"studies/actuator-dynamics/analysis/secondary_publication_plots.py",prep/"prepared/actuator",staging/"secondary"), blocked_by=("historical-prep-health",))

    def export_belt():
        work=support/"belt_input_copy"; shutil.copytree(prep/"prepared/belt",work)
        return worker_family("belt",work,staging/"belt")
    step("export-belt", export_belt, blocked_by=("historical-prep-health","belt-health-refresh"))

    def export_course():
        script=HERE/"studies/course-tuning/analysis/course_publication_export.py"
        run_capture([sys.executable,script,"--bundle-dir",prep/"prepared/course","--output-dir",staging/"course","--log-dir",logs/"course"],cwd=script.parent,log=logs/"export_course.log")
        return {"script_sha256":sha(script),"course_plot_inputs_sha256":sha(prep/"prepared/course/course_plot_inputs.npz")}
    step("export-course", export_course, blocked_by=("historical-prep-health",))

    stage_for={"energy":"energy","solver":"solver","closure":"closure","ballew":"ballew","primary":"primary","secondary":"secondary","belt":"belt","course":"course"}
    def locate(stage: Path, basename: str):
        hits=[p for p in stage.rglob(basename) if p.is_file()]
        if len(hits)!=1: raise FileNotFoundError(f"expected exactly one {basename} below {stage}, found {hits}")
        return hits[0]
    for family, rels in FAMILY_ASSETS.items():
        export_step="export-"+family
        status=next((x["status"] for x in steps if x["id"]==export_step),"MISSING")
        if status!="PASS": continue
        for rel in rels:
            src=locate(staging/stage_for[family],Path(rel).name)
            dst=figures/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
            png=src.with_suffix(".png")
            if png.is_file(): companions[rel]=png

    def inventory_check():
        missing=[x for x in EXPECTED_ASSETS if not (figures/x).is_file()]
        extra=[p.relative_to(figures).as_posix() for p in figures.rglob('*') if p.is_file() and p.relative_to(figures).as_posix() not in EXPECTED_ASSETS]
        if missing: raise MissingInput("missing final manuscript assets: "+repr(missing))
        if extra: raise ValueError("unexpected files in final manuscript asset tree: "+repr(extra))
        return {"count":len(EXPECTED_ASSETS),"missing":[],"extra":[]}
    step("manuscript-inventory", inventory_check)

    assets={}; render_fail=[]; visual={}
    for rel in EXPECTED_ASSETS:
        pth=figures/rel
        if not pth.is_file(): continue
        check=png_check(pth) if pth.suffix.lower()==".png" else pdf_check(pth)
        if not check.get("ok"): render_fail.append(rel)
        meta={"sha256":sha(pth),"bytes":pth.stat().st_size,"render_check":check}
        reference_same = REPO/"docs/CVT_Module_Formulation/figures/results"/rel
        if reference_same.is_file():
            ref_bytes=reference_same.stat().st_size
            meta["reference_sha256"]=sha(reference_same)
            meta["reference_bytes"]=ref_bytes
            meta["size_delta_bytes"]=pth.stat().st_size-ref_bytes
            meta["size_ratio_vs_reference"]=(pth.stat().st_size/ref_bytes if ref_bytes else None)
        else:
            meta["reference_same_format_missing"]=True
        assets[rel]=meta
        # Compare using PNG companions so scientific traces and presentation can
        # be assessed without depending on a PDF rasterizer.
        cand_png = pth if pth.suffix.lower()==".png" else companions.get(rel)
        ref_png = REPO/"docs/CVT_Module_Formulation/figures/results"/Path(rel).with_suffix(".png")
        if cand_png and Path(cand_png).is_file():
            visual[rel]=image_compare(Path(cand_png),ref_png)
    if render_fail: steps.append({"id":"render-checks","status":"FAIL","detail":repr(render_fail),"elapsed_s":0.0})
    else: steps.append({"id":"render-checks","status":"PASS","detail":"","elapsed_s":0.0,"result":{"checked":len(assets)}})

    visual_bad=[]
    for rel in EXPECTED_ASSETS:
        if rel not in assets:
            continue
        row=visual.get(rel)
        if not row or row.get("status") in {"MISSING_REFERENCE","DIMENSION_DIFFERENCE","COMPARE_ERROR"}:
            visual_bad.append((rel, None if not row else row.get("status")))
    if visual_bad:
        steps.append({"id":"visual-comparisons","status":"FAIL","detail":repr(visual_bad),"elapsed_s":0.0})
    else:
        steps.append({"id":"visual-comparisons","status":"PASS","detail":"","elapsed_s":0.0,"result":{"checked":len(visual)}})

    # Table/value handoff is a read-only harvest of exporter-produced values and provenance.
    handoff={}
    for pth in sorted(staging.rglob("*.json")):
        if any(k in pth.name for k in ("values","provenance","metrics")):
            rel=pth.relative_to(staging).as_posix(); entry={"sha256":sha(pth),"bytes":pth.stat().st_size}
            if pth.stat().st_size < 2_000_000:
                try:
                    content=load_json(pth)
                    if has_nonfinite_json(content):
                        entry["content_omitted"]="source JSON contains non-finite numeric values; exact source retained by SHA-256"
                    else:
                        entry["content"]=content
                except Exception as e:
                    entry["content_omitted"]="source JSON could not be embedded: "+repr(e)
            handoff[rel]=entry
    write_json(support/"table_value_handoff.json",{"schema":1,"files":handoff})

    source_files=[
        Path(__file__).resolve(), HERE/"results_health/figure_only_worker.py", HERE/"results_health/belt.py",
        HERE/"studies/course-tuning/analysis/course_publication_export.py",
        HERE/"studies/actuator-dynamics/analysis/primary_publication_plots.py",
        HERE/"studies/actuator-dynamics/analysis/secondary_publication_plots.py",
        HERE/"studies/ballew-2015/analysis/publication_plots.py",
        HERE/"studies/energy-consistency/analysis/publication_plots.py",
        HERE/"studies/solver-convergence/analysis/publication_plots.py",
        HERE/"studies/closure-conditioning/analysis/publication_plots.py",
        HERE/"studies/reduced-belt-transients/analysis/publication_plots.py",
    ]
    export_identity={str(x.relative_to(REPO)).replace('\\','/'):{"sha256":sha(x)} for x in source_files if x.is_file()}
    family_provenance={}
    for family in FAMILY_ASSETS:
        stage=staging/stage_for[family]
        records=[]
        if stage.is_dir():
            for pth in sorted(stage.rglob("*.json")):
                if any(token in pth.name.lower() for token in ("provenance","manifest","values","metrics","audit")):
                    records.append({"path":pth.relative_to(staging).as_posix(),"sha256":sha(pth),"bytes":pth.stat().st_size})
        family_provenance[family]=records
    numerical_identity={
        "frozen_simulator":"cinder-cvt 1.1.2","mechanics_commit":MECHANICS_COMMIT,
        "all_run":ALL_RUN_ID,"ballew_corrected_run":BALLEW_RUN_ID,"localized_prep":PREP_RUN_ID,
        "course_plot_inputs_sha256": COURSE_NPZ_SHA256,
        "solver_retained_root":str(solver),"closure_retained_root":str(closure),
    }
    manifest={"schema":1,"numerical_execution_identity":numerical_identity,"export_identity":{"git_head":preflight["checks"].get("git_head"),"baseline_head":BASELINE_HEAD,"dirty_status":preflight["checks"].get("git_status_porcelain",""),"files":export_identity},"manuscript_inventory":{"count":len(EXPECTED_ASSETS),"imports":list(EXPECTED_ASSETS),"tex_sha256":sha(REPO/"docs/CVT_Module_Formulation/CVT_Module_Formulation.tex")},"family_provenance":family_provenance,"optimization":{"performed":False,"policy":"No blanket compression/restyling; exporters keep their native PDF/PNG settings."},"assets":assets,"visual_comparisons":visual}
    write_json(out/"final_asset_manifest.json",manifest)
    write_json(out/"input_output_provenance.json",manifest)
    write_json(out/"visual_comparisons.json",visual)

    limitations=[]
    source_ref=HERE/"studies/course-tuning/analysis/course_export_reference/451/current_asset_reference.json"
    if source_ref.is_file():
        limitations.append("The later original Section 4.5.1 plotting source was not recovered; the three current 4.5.1 figures use an explicit presentation reconstruction anchored to current committed assets while retaining recovered v4 numerical selections.")
    limitations.append("This runner exports from accepted retained evidence only; it does not re-integrate simulations or repeat historical solver/root searches.")
    bad=[x for x in steps if x["status"]!="PASS"]
    ready=(not bad and len(assets)==len(EXPECTED_ASSETS) and not render_fail)
    report={"schema":1,"kind":"cinder-v1.1.2-figure-only","started_epoch":started,"elapsed_s":round(time.time()-started,3),"preflight":preflight,"steps":steps,"counts":{s:sum(x["status"]==s for x in steps) for s in ("PASS","FAIL","MISSING","BLOCKED")},"expected_asset_count":len(EXPECTED_ASSETS),"actual_asset_count":len(assets),"visual_comparison_count":len(visual),"ready_to_freeze":ready,"assets":assets,"limitations":limitations,"simulations_reexecuted":0,"broad_solver_or_closure_searches_reexecuted":0,"manuscript_overwritten":False}
    write_json(out/"health_report.json",report)
    write_html_report(out/"health_report.html",report)

    # Compact shareable summary ZIP: reports, logs, manifests and table handoff.
    zpath=out/"figure_only_summary.zip"
    with zipfile.ZipFile(zpath,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for root in (out/"health_report.json",out/"health_report.html",out/"final_asset_manifest.json",out/"input_output_provenance.json",out/"visual_comparisons.json",support/"table_value_handoff.json"):
            if root.is_file(): z.write(root,root.relative_to(out).as_posix())
        for root in sorted(logs.rglob('*')):
            if root.is_file(): z.write(root,root.relative_to(out).as_posix())
    print(json.dumps({"ready_to_freeze":ready,"counts":report["counts"],"assets":len(assets),"output":str(out),"summary_zip":str(zpath)},indent=2))
    return 0 if ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
