"""Publication figures for Results 4.2.3 from checked numerical evidence.

Canonical invocation: python studies/solver-convergence/run.py --plot-only
No contours or decision boundaries are inferred between sampled cells.
Continuous traces are drawn separately on each retained hybrid segment.
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import NullFormatter
import numpy as np
from .evidence import REPO, gross_rms, write_json, digest
from .verification import audit, formal_module

BLUE, ORANGE, GREEN, GREY = "#21618c", "#b44e2b", "#38735c", "#b4b7bb"
STYLE = {
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 9,
    "axes.labelsize": 9, "axes.titlesize": 10, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.fontsize": 8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.linewidth": .6, "lines.linewidth": 1.1,
    "pdf.fonttype": 42, "savefig.dpi": 300,
}

def sci(value):
    exponent = int(np.floor(np.log10(value)))
    mantissa = int(round(value / 10**exponent))
    return rf"$10^{{{exponent}}}$" if mantissa == 1 else rf"${mantissa}\!\times\!10^{{{exponent}}}$"

def save(fig, out, name):
    fig.savefig(out / f"{name}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / f"{name}.png")
    plt.close(fig)

def refinement(main, atol, values, out):
    rtols = sorted({r["relative_tolerance"] for r in main}, reverse=True)
    steps = sorted({r["max_step"] for r in main}, reverse=True)
    lookup = {(r["relative_tolerance"], r["max_step"]): r for r in main}
    error = np.array([[lookup[(r, s)]["trajectory_rms_normalized"] for r in rtols] for s in steps])
    fig = plt.figure(figsize=(6.5, 4.0))
    gs = fig.add_gridspec(2, 2, height_ratios=(1.05, 1), width_ratios=(1, .028),
                         left=.10, right=.92, bottom=.105, top=.93, hspace=.69, wspace=.045)
    ax = fig.add_subplot(gs[0, 0])
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#eeeeee")
    im = ax.imshow(np.ma.masked_invalid(error), aspect="auto", cmap=cmap,
                   norm=LogNorm(1e-8, 1e-3))
    ax.set_xticks(range(8), [sci(r) for r in rtols])
    ax.set_yticks(range(5), [f"{s*1000:g}" for s in steps])
    ax.set_ylabel("Maximum step [ms]")
    ax.set_xlabel(r"Relative tolerance; $\mathrm{atol}=10^{-3}\mathrm{rtol}$", labelpad=3)
    ax.set_title("(a) Formal sweep: state error and all-guard acceptance", loc="left", pad=7)
    for iy, s in enumerate(steps):
        for ix, r in enumerate(rtols):
            row = lookup[(r, s)]
            if row["passes_review_guards"]:
                ax.scatter(ix, iy, s=34, facecolors="none", edgecolors="white", linewidths=1)
            elif row["run_status"] != "completed":
                ax.text(ix, iy, "F", ha="center", va="center", fontsize=9, color="#772c22")
            elif not row["transition_signature_match"]:
                ax.text(ix, iy, "×", ha="center", va="center", fontsize=11, color="#333333")
    can = values["canonical"]
    ix, iy = rtols.index(can["relative_tolerance"]), steps.index(can["max_step"])
    ax.add_patch(Rectangle((ix-.47, iy-.45), .94, .9, fill=False, edgecolor="#ffcf55", lw=1.6))
    cb = fig.colorbar(im, cax=fig.add_subplot(gs[0, 1]))
    cb.set_label("Five-state aligned RMS", fontsize=8)
    ax = fig.add_subplot(gs[1, :])
    xs = np.array([r["absolute_tolerance"] for r in atol])
    ax.axhline(1, color="#4c4c4c", ls="--", lw=.8)
    styles = [("trajectory_rms_normalized", "State RMS", BLUE, "o"),
              ("trajectory_max_abs_normalized", "State maximum", ORANGE, "s"),
              ("maximum_event_time_error_s", "Event time", GREEN, "^"),
              ("regime_mismatch_fraction", "Regime duration", "#775b8d", "D")]
    for key, label, color, marker in styles:
        ys = np.array([r[key] / values["guards"][key] for r in atol])
        ax.scatter(xs, ys, s=23, marker=marker, color=color, label=label, zorder=3)
    for r in atol:
        if not r["transition_signature_match"]:
            ax.axvline(r["absolute_tolerance"], color="#cccccc", lw=5, alpha=.35)
            ax.text(r["absolute_tolerance"], 4, "×", ha="center", va="center", fontsize=11)
    ax.axvline(1e-7, color="#ba912c", lw=.8, alpha=.8)
    ax.set(xscale="log", yscale="log", xlim=(1.7e-5, .6e-8), ylim=(8e-5, 7))
    ax.set_xticks(xs, [sci(x) for x in xs])
    ax.minorticks_off()
    ax.set_yticks([1e-4, 1e-2, 1], [r"$10^{-4}$", r"$10^{-2}$", "1"])
    ax.set_ylabel("Error / guard limit")
    ax.set_xlabel(r"Absolute tolerance at $\mathrm{rtol}=10^{-4}$ and 10 ms maximum step", labelpad=3)
    ax.set_title("(b) Independent absolute-tolerance sweep", loc="left", pad=21)
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(-.008, 1.005), frameon=False,
              borderaxespad=0, handletextpad=.3, columnspacing=1)
    ax.grid(axis="y", color="#eeeeee", lw=.5)
    save(fig, out, "solver_refinement")

def contact_kind(mode):
    if "DEADZONE:" in mode:
        return "separated"
    if "LOW_RATIO_SEAT:" in mode:
        return "seated"
    return "engaged"

def history(dense, caches, values, out):
    fig = plt.figure(figsize=(6.5, 4.2))
    gs = fig.add_gridspec(2, 2, height_ratios=(1.3, .8),
                         left=.105, right=.98, bottom=.115, top=.94, hspace=.75, wspace=.4)
    ax = fig.add_subplot(gs[0, 0])
    complete = [r for r in dense if r["run_status"] == "completed"]
    for status, color, label, z in [(True, GREY, "Exact signature (4,072)", 1),
                                  (False, ORANGE, "Different signature (609)", 2)]:
        group = [r for r in complete if r["transition_signature_match"] == status]
        ax.scatter([r["native_solver_point_count"] for r in group], [gross_rms(r) for r in group],
                   s=4, color=color, alpha=.65, linewidths=0, rasterized=True, label=label, zorder=z)
    ax.scatter(values["selected_archived_native_point_count"], values["selected_archived_gross_rms"],
               marker="*", s=80, facecolor="#ffcf55", edgecolor="#444444", lw=.5, zorder=5)
    ax.set(xscale="log", yscale="log", xlabel="Native solver points", ylabel="Four-state gross RMS")
    ax.set_title("(a) Exploratory population", loc="left", pad=7)
    ax.set_xticks([200, 500, 1000, 2000], ["200", "500", "1,000", "2,000"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.legend(loc="upper right", frameon=False, markerscale=2, fontsize=7.5, handletextpad=.2)
    ax.grid(color="#eeeeee", lw=.5)
    ax = fig.add_subplot(gs[0, 1])
    formal = formal_module()
    for name, color, style, label in [("reference", BLUE, "-", "Tight reference"),
                                    ("selected", ORANGE, "--", "Selected replay")]:
        cache = caches[name]
        for i in range(len(cache["segments"])):
            seg = formal.unpack_segment_trace(cache["payload"], i)
            time = seg["start_time_s"] + seg["phase"] * (seg["end_time_s"]-seg["start_time_s"])
            ax.plot(time, seg["shift_m"]*1000, color=color, ls=style, label=label if i == 0 else None)
    ax.set(xlim=(0, 10), ylim=(-.6, 20), xlabel="Time after launch [s]", ylabel="Shift position [mm]")
    ax.set_title("(b) Gross shift motion", loc="left", pad=7)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.grid(color="#eeeeee", lw=.5)
    ax = fig.add_subplot(gs[1, :])
    colors = {"separated": "#d2d5d9", "engaged": BLUE, "seated": GREEN}
    for y, name in [(1, "reference"), (0, "selected")]:
        for seg in caches[name]["segments"]:
            left, right = 1000*seg["start_time_s"], 1000*seg["end_time_s"]
            if right < 61.5 or left > 66.5:
                continue
            ax.broken_barh([(max(left, 61.5), min(right, 66.5)-max(left, 61.5))],
                          (y-.18, .36), facecolors=colors[contact_kind(seg["mode"])], linewidth=0)
        seat = next(r["time_s"]*1000 for r in caches[name]["events"] if "LOW_RATIO_SEAT:" in r["next_mode"])
        ax.plot([seat, seat], [y-.24, y+.24], color="black", lw=.7)
        ax.annotate(f"seated {seat:.3f} ms", (seat, y-.2), (seat-.07, y-.41),
                    fontsize=7.5, ha="right", va="center")
    ax.set(xlim=(61.5, 66.5), ylim=(-.57, 1.65), xlabel="Time after launch [ms]")
    ax.set_yticks([1, 0], ["Reference\n16 events", "Replay\n12 events"])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_title("(c) Native contact and seating history", loc="left", pad=18)
    ax.legend(handles=[Patch(facecolor=colors[k], label=l) for k, l in
                       [("separated", "Primary separated"), ("engaged", "Engaged, free shift"),
                        ("seated", "Low-ratio support")]],
              ncol=3, frameon=False, loc="lower left", bbox_to_anchor=(-.005, 1.02),
              borderaxespad=0, handlelength=1.1, columnspacing=1.5)
    save(fig, out, "gross_motion_hybrid_history")

def publish(artifacts, out=None):
    artifacts = Path(artifacts)
    out = Path(out) if out is not None else REPO / "docs/CVT_Module_Formulation/figures/results/verification"
    out.mkdir(parents=True, exist_ok=True)
    values, main, atol, dense, caches = audit(artifacts)
    with plt.rc_context(STYLE):
        refinement(main, atol, values, out)
        history(dense, caches, values, out)
    write_json(out / "solver_convergence_values.json", values)
    write_json(out / "solver_convergence_provenance.json", {
        "run_id": values["run_id"], "script": str(Path(__file__).relative_to(REPO)),
        "script_sha256": digest(__file__),
        "command": "python studies/solver-convergence/run.py --plot-only",
        "figure_labels": ["fig:verification_solver_refinement", "fig:verification_gross_hybrid_agreement"],
        "figure_width_inches": 6.5,
        "figure_1": "All 40 main cells and all 7 absolute-tolerance rows. No contours or interpolated pass boundary. Missing aligned metrics remain undefined. All four guards and signature retained.",
        "figure_2": "All 4681 completed dense rows, exact signature grouping, four-state absolute-time RMS excluding shift speed. 264 failures have no trajectory norm. Selected median settings replayed once. Shift plotted by native segment, never joined across resets; timeline uses native absolute time, including zero-duration transitions in supporting records.",
        "verification_scope": values["scope"],
        "evidence_record_sha256": digest(artifacts / "execution_provenance.json"),
    })
    print(f"Verified and published {values['run_id']} to {out}")
