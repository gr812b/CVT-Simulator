"""Publication energy accounting for manuscript Section 4.2.2.

Use canonical run.py --plot-only; this module never runs a simulation. PDF and
PNG are exported at the 6.5-inch manuscript width, with deterministic metadata.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from analysis.execution_record import digest, verify_execution_record
from analysis.verification import verify

STUDY = Path(__file__).resolve().parents[1]
REPOSITORY = STUDY.parents[3]
DEFAULT_OUTPUT = REPOSITORY / "docs/CVT_Module_Formulation/figures/results/verification"
BLUE, ORANGE, GREEN = "#245b82", "#ad4c24", "#517b67"
SIZE = (6.5, 4.6)


def series(ax, groups, x, y, *, scale=1.0, **style):
    """Plot each smooth segment separately, preserving native event sides."""
    for rows in groups.values():
        ax.plot([r[x] for r in rows], [scale * r[y] for r in rows], **style)


def make_figure(data: dict, output: Path):
    style = {"font.family": "serif", "font.serif": ["STIXGeneral"],
             "mathtext.fontset": "stix", "font.size": 9.5,
             "axes.labelsize": 9.5, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
             "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False}
    with plt.rc_context(style):
        fig = plt.figure(figsize=SIZE)
        grid = fig.add_gridspec(2, 2, left=.09, right=.98, bottom=.105, top=.94,
                               hspace=.57, wspace=.36)
        a = fig.add_subplot(grid[0, 0])
        b = fig.add_subplot(grid[0, 1])
        c = fig.add_subplot(grid[1, 0])
        d = fig.add_subplot(grid[1, 1])
        nominal = data["groups"]["nominal"]
        series(a, nominal, "time_s", "primary_boundary_work_J", scale=.001, color=BLUE, lw=1.15)
        series(a, nominal, "time_s", "secondary_boundary_work_J", scale=.001, color=ORANGE, lw=1.15, ls="--")
        series(a, nominal, "time_s", "kinetic_energy_change_J", scale=.001, color=GREEN, lw=1.25, ls="-.")
        a.axhline(0, color=".45", lw=.7, zorder=0)
        a.set_title("(a) Shaft work and kinetic energy", loc="left", fontsize=10.5, pad=7)
        a.set(xlim=(0, 10), ylim=(-20, 75), xlabel="Time [s]", ylabel="Energy [kJ]")
        a.legend(handles=[
            Line2D([], [], color=BLUE, lw=1.15, label="Primary work"),
            Line2D([], [], color=GREEN, lw=1.25, ls="-.", label="Kinetic-energy increase"),
            Line2D([], [], color=ORANGE, lw=1.15, ls="--", label="Secondary work")],
            loc="upper left", frameon=False, fontsize=8.5, handlelength=2.2, borderaxespad=.3)
        for label, colour, linestyle in (("nominal", BLUE, "-"), ("tight", ORANGE, "--")):
            series(b, data["groups"][label], "time_s", "balance_residual_J", color=colour, lw=1.05, ls=linestyle)
        b.axhline(0, color=".45", lw=.7, zorder=0)
        b.set_title("(b) Signed energy remainder", loc="left", fontsize=10.5, pad=7)
        b.set(xlim=(0, 10), xlabel="Time [s]", ylabel=r"$R_E$ [J]")
        b.legend(handles=[Line2D([], [], color=BLUE, lw=1.05, label="Nominal integration"),
                          Line2D([], [], color=ORANGE, ls="--", lw=1.05, label="Tighter integration")],
                 loc="upper left", frameon=False, fontsize=8.5, handlelength=2.2)
        stop_time = next(r["time_s"] for r in data["captures"]["nominal"]
                         if r["reason"] == "upper_stop_reached_perfectly_inelastic_impact")
        b.axvline(stop_time, color=".55", lw=.7, ls=":", zorder=0)
        b.annotate("Upper stop\nsee (c)", xy=(stop_time, 0),
                   xytext=(8.6, .005), ha="center", va="center", fontsize=8.5,
                   arrowprops={"arrowstyle": "-", "color": ".4", "lw": .65})
        for label, colour, linestyle in (("nominal", BLUE, "-"), ("tight", ORANGE, "--")):
            event = next(r for r in data["captures"][label] if r["reason"] == "upper_stop_reached_perfectly_inelastic_impact")
            t0 = event["time_s"]
            for rows in data["groups"][label].values():
                selected = [r for r in rows if -.02 <= r["time_s"] - t0 <= .04]
                c.plot([1000 * (r["time_s"] - t0) for r in selected],
                       [r["balance_residual_J"] for r in selected], color=colour, lw=1.05, ls=linestyle)
            i = int(event["transition_index"])
            before, after = data["groups"][label][i][-1], data["groups"][label][i+1][0]
            c.plot(0, before["balance_residual_J"], "o", ms=5.5, mfc="white", mec=colour, zorder=4)
            c.plot(0, after["balance_residual_J"], "+", ms=4, color=colour, mew=.9, zorder=5)
        c.axvline(0, color=".5", lw=.8, ls=":")
        c.axhline(0, color=".5", lw=.7)
        c.set_title("(c) Detail at the upper stop", loc="left", fontsize=10.5, pad=7)
        c.set(xlim=(-20, 40), xlabel="Time from upper-stop arrival [ms]", ylabel=r"$R_E$ [J]")
        c.text(.03, .96, "Before/after values\ncoincide at arrival", transform=c.transAxes, fontsize=8.5, va="top")
        c.text(24, .025, "Nominal", color=BLUE, fontsize=8.5, va="bottom")
        c.text(24, -.022, "Tighter", color=ORANGE, fontsize=8.5, va="bottom")
        q = data["quadrature"]
        x = np.array([r["audit_step_s"] * 1000 for r in q])
        y = np.array([r["sum_continuous_raw_defect_J"] for r in q])
        extrapolate = q[-1]["richardson_zero_step_estimate_J"]
        d.plot(x, y, "o-", color=BLUE, ms=4, lw=.85)
        d.axhline(extrapolate, color=ORANGE, lw=.9, ls="--")
        d.set_title("(d) Refining the work integral", loc="left", fontsize=10.5, pad=7)
        d.set_xscale("log", base=2)
        d.set(xlim=(6, .52), ylim=(0, .105), xlabel="Power-evaluation interval, $h$ [ms]",
              ylabel=r"Continuous remainder, $D(h)$ [J]")
        d.set_xticks(x, ["5", "2.5", "1.25", "0.625"])
        d.text(.97, .96, "Same calculated motion", ha="right", va="top", transform=d.transAxes, fontsize=8.5)
        d.text(.97, .04, f"Zero-spacing estimate: {extrapolate:+.4f} J", ha="right", va="bottom",
               transform=d.transAxes, fontsize=8.5, color=ORANGE)
        for ax in (a, b, c, d):
            ax.grid(color=".90", lw=.5)
            ax.set_axisbelow(True)
        output.mkdir(parents=True, exist_ok=True)
        fig.savefig(output / "energy_balance.pdf", metadata={"Creator": "CINDER energy-consistency publication_plots.py",
                                                             "CreationDate": None, "ModDate": None})
        fig.savefig(output / "energy_balance.png", dpi=220)
        plt.close(fig)


def publish(artifacts: Path, output: Path | None = None) -> dict:
    output = (output or DEFAULT_OUTPUT).resolve()
    subprocess.run([sys.executable, str(STUDY.parents[1] / "verify_environment.py")], check=True)
    record = verify_execution_record(artifacts)
    spec = json.loads((STUDY / "study.json").read_text())
    data, checks = verify(artifacts, spec)
    make_figure(data, output)
    values = {"run_id": record["run_id"], "checks": checks,
              "nominal": data["summary"]["nominal_energy_balance"],
              "tight": data["summary"]["tight_energy_balance"],
              "final_energy_ledger": {
                  label: {key: rows[-1][key] for key in (
                      "primary_boundary_work_J", "secondary_boundary_work_J", "external_work_J",
                      "kinetic_energy_change_J", "potential_energy_change_J", "slip_dissipation_J",
                      "impact_capture_dissipation_J", "balance_residual_J")}
                  for label, rows in data["traces"].items()},
              "quadrature": data["quadrature"],
              "capture_events": data["captures"],
              "solver_refinement": data["summary"]["solver_refinement"]}
    (output / "energy_balance_values.json").write_text(json.dumps(values, indent=2) + "\n")
    provenance = {
        "manuscript_label": "fig:verification_energy_balance",
        "manuscript_asset": "docs/CVT_Module_Formulation/figures/results/verification/energy_balance.pdf",
        "run_id": record["run_id"],
        "execution_record_sha256": digest(artifacts / "execution_provenance.json"),
        "mechanics_version": record["packages"]["cinder-cvt"],
        "mechanics_commit": record["mechanics_commit"],
        "plotting_sources": {name: digest(STUDY / "analysis" / name)
                             for name in ("publication_plots.py", "verification.py", "execution_record.py")},
        "size_inches": list(SIZE),
        "transformations": {
            "selection": "Complete 0-10 s nominal and tight canonical trajectories. No event, regime, negative residual or endpoint excluded.",
            "work_storage": "J to kJ only. Separate signed primary and secondary boundary work and kinetic-energy increase, nominal solution only. Both attached boundary inertias are included in kinetic energy. The ledger supplies spring storage and losses; no unresolved totals overlay is used as evidence of closure.",
            "residual": "Signed dimensional W - storage - kinetic slip - discrete capture. No sticking-drift work subtraction. Same 0.625 ms maximum audit spacing for both ODE settings.",
            "events": "Both exact native sides retained at every equal-time event. Separate line per continuous segment; no smoothing or trapezoid across resets. Capture loss added only to outgoing side.",
            "upper_stop_detail": "Each trajectory uses its own native upper-stop event time as zero, with -20 to +40 ms shown. Open circles (incoming) and crosses (outgoing) coincide in residual. This is a display alignment, not an event-aligned convergence metric.",
            "quadrature": "Sum of continuous-segment defects at 5, 2.5, 1.25, 0.625 ms maximum spacing, each segment at least 12 intervals. Nominal trajectory held fixed. Actual h on a descending base-2 logarithmic axis: each step right halves the maximum spacing. Connecting segments guide the eye and are not a fitted error model. The horizontal second-order Richardson extrapolate uses only two finest spacings; not an uncertainty or remaining-quadrature-error bar.",
        },
        "checks": checks,
        "outputs": {name: digest(output / name) for name in
                    ("energy_balance.pdf", "energy_balance.png", "energy_balance_values.json")},
        "author_status": "ready_for_author_review_not_author_accepted",
    }
    (output / "energy_balance_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    return provenance
