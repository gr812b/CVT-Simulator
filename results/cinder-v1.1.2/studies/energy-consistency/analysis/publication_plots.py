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
SIZE = (6.5, 4.25)


def series(ax, groups, x, y, *, scale=1.0, **style):
    """Plot each smooth segment separately, preserving native event sides."""
    for rows in groups.values():
        ax.plot([r[x] for r in rows], [scale * r[y] for r in rows], **style)


def make_figure(data: dict, output: Path):
    style = {"font.family": "serif", "font.serif": ["STIXGeneral"],
             "mathtext.fontset": "stix", "font.size": 9,
             "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
             "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False}
    with plt.rc_context(style):
        fig = plt.figure(figsize=SIZE)
        grid = fig.add_gridspec(2, 2, left=.085, right=.98, bottom=.12, top=.92,
                               hspace=.57, wspace=.35)
        a = fig.add_subplot(grid[0, 0])
        b = fig.add_subplot(grid[0, 1])
        c = fig.add_subplot(grid[1, 0])
        d = fig.add_subplot(grid[1, 1])
        nominal = data["groups"]["nominal"]
        series(a, nominal, "time_s", "stored_energy_change_J", scale=.001, color=GREEN, lw=1.15)
        series(a, nominal, "time_s", "accounted_energy_J", scale=.001, color=ORANGE, lw=2.2)
        series(a, nominal, "time_s", "external_work_J", scale=.001, color=BLUE, lw=1.15, ls=(0, (4, 2)))
        a.set_title("(a) Work and its accounting", loc="left", fontsize=10, pad=6)
        a.set(xlim=(0, 10), xlabel="Time [s]", ylabel="Energy [kJ]")
        a.legend(handles=[
            Line2D([], [], color=BLUE, ls="--", lw=1.15, label=r"Net work $W_{\mathrm{B}}$"),
            Line2D([], [], color=ORANGE, lw=2.2, label=r"Storage + slip + capture"),
            Line2D([], [], color=GREEN, lw=1.15, label=r"Storage $\Delta E_{\mathrm{stored}}$")],
            loc="upper left", frameon=False, fontsize=8, handlelength=2.4, borderaxespad=.3)
        for label, colour, linestyle in (("nominal", BLUE, "-"), ("tight", ORANGE, "--")):
            series(b, data["groups"][label], "time_s", "balance_residual_J", color=colour, lw=1.05, ls=linestyle)
        b.axhline(0, color=".45", lw=.7, zorder=0)
        b.set_title("(b) Signed balance residual", loc="left", fontsize=10, pad=6)
        b.set(xlim=(0, 10), xlabel="Time [s]", ylabel=r"$R_E$ [J]")
        b.legend(handles=[Line2D([], [], color=BLUE, lw=1.05, label="Nominal ODE"),
                          Line2D([], [], color=ORANGE, ls="--", lw=1.05, label="Tighter ODE")],
                 loc="upper left", frameon=False, fontsize=8, handlelength=2.2)
        for label, colour, linestyle in (("nominal", BLUE, "-"), ("tight", ORANGE, "--")):
            event = next(r for r in data["captures"][label] if r["reason"] == "upper_stop_reached_perfectly_inelastic_impact")
            t0 = event["time_s"]
            for rows in data["groups"][label].values():
                selected = [r for r in rows if -.02 <= r["time_s"] - t0 <= .04]
                c.plot([1000 * (r["time_s"] - t0) for r in selected],
                       [r["balance_residual_J"] for r in selected], color=colour, lw=1.05, ls=linestyle)
            i = int(event["transition_index"])
            for row in (data["groups"][label][i][-1], data["groups"][label][i+1][0]):
                c.plot(0, row["balance_residual_J"], "o", ms=4, mfc="white", mec=colour, zorder=4)
        c.axvline(0, color=".5", lw=.8, ls=":")
        c.axhline(0, color=".5", lw=.7)
        c.set_title("(c) Resolving the upper-stop interval", loc="left", fontsize=10, pad=6)
        c.set(xlim=(-20, 40), xlabel="Time from each upper-stop capture [ms]", ylabel=r"$R_E$ [J]")
        c.text(.03, .96, "Native sides\ncoincide at capture", transform=c.transAxes, fontsize=8, va="top")
        q = data["quadrature"]
        x = np.array([r["audit_step_s"] * 1000 for r in q])**2
        y = np.array([r["sum_continuous_raw_defect_J"] for r in q])
        extrapolate = q[-1]["richardson_zero_step_estimate_J"]
        d.plot(x, y, "o", color=BLUE, ms=4)
        d.axhline(extrapolate, color=ORANGE, lw=.9, ls="--")
        # Only the two finest spacings define the stated second-order extrapolate.
        d.plot([0, x[-2]], [extrapolate, y[-2]], color=BLUE, lw=.8)
        d.plot(0, extrapolate, marker="o", ms=4.5, mec=ORANGE, mfc="white", clip_on=False)
        d.set_title("(d) Fixed-trajectory quadrature", loc="left", fontsize=10, pad=6)
        d.set(xlim=(-.7, 26), xlabel=r"Audit spacing squared $h^2$ [ms$^2$]",
              ylabel="Continuous defect [J]")
        d.set_xticks([0, 10, 20, 25])
        d.text(.97, .94, "Nominal trajectory", ha="right", va="top", transform=d.transAxes, fontsize=8)
        d.text(.97, .08, f"Zero-spacing estimate\n{extrapolate:+.6f} J", ha="right", va="bottom",
               transform=d.transAxes, fontsize=8, color=ORANGE)
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
            "work_storage": "J to kJ only. Both attached boundary inertias are included in retained kinetic energy. Net work adds the two signed external-torque works.",
            "residual": "Signed dimensional W - storage - kinetic slip - discrete capture. No sticking-drift work subtraction. Same 0.625 ms maximum audit spacing for both ODE settings.",
            "events": "Both exact native sides retained at every equal-time event. Separate line per continuous segment; no smoothing or trapezoid across resets. Capture loss added only to outgoing side.",
            "upper_stop_detail": "Each trajectory uses its own native upper-stop event time as zero, with -20 to +40 ms shown. Open circles show both native sides, which coincide in residual. This is a display alignment, not an event-aligned convergence metric.",
            "quadrature": "Sum of continuous-segment defects at 5, 2.5, 1.25, 0.625 ms maximum spacing, each segment at least 12 intervals. Nominal trajectory held fixed. Second-order Richardson extrapolate uses only two finest spacings; not an uncertainty or remaining-quadrature-error bar.",
        },
        "checks": checks,
        "outputs": {name: digest(output / name) for name in
                    ("energy_balance.pdf", "energy_balance.png", "energy_balance_values.json")},
        "author_status": "ready_for_author_review_not_author_accepted",
    }
    (output / "energy_balance_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    return provenance
