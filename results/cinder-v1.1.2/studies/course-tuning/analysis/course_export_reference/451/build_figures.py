"""Reconstruct the three current Section 4.5.1 manuscript figures.

Numerical selections and mechanism/ramp calculations are inherited unchanged
from the recovered Section_4_5_1_Revision_v4 exporter.  The later paper-facing
source was not retained in the repository, so the presentation below is an
explicit reconstruction against the three PNG assets committed at PR #505 head
953d1b0423d0655002271de2af43a72c47cff87e.  It changes only presentation:
current filename, limits/annotations, panel wording, layout and export size.
No simulation, smoothing, interpolation or trajectory filtering is performed.
"""
from pathlib import Path
import json
import numpy as np
import course_csvframe as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "figures/results/course"
OUT.mkdir(parents=True, exist_ok=True)
CASES = ["R00", "W85", "P300", "RC10", "R26B7", "RC40L"]
COLORS = dict(zip(CASES, plt.get_cmap("tab10").colors[:6]))
META = json.loads((ROOT / "plot_provenance.json").read_text(encoding="utf-8"))

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.labelsize": 9, "axes.titlesize": 9,
    "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.linewidth": .7, "lines.linewidth": 1.5,
    "axes.axisbelow": True,
})


def grid(ax):
    ax.grid(True, color="#d6d8dc", alpha=.65, linewidth=.6)
    ax.tick_params(width=.7, length=3)


def save(fig, name, dpi):
    fig.savefig(OUT / name, dpi=dpi, bbox_inches="tight", pad_inches=.04)
    plt.close(fig)


# Complete opening motion through the first 120 m, including disengagement,
# launch slip, supported motion and free shift.  The dashed lines are geometry
# only; they are not fitted speed curves.
fig, ax = plt.subplots(figsize=(11.58, 7.06))
fig.subplots_adjust(left=.08, right=.992, bottom=.11, top=.965)
x = np.linspace(0, 4650, 400)
ax.plot(x, x / META["low_ratio_rp_over_rs"], color="#e78ac3", ls="--", lw=1.15, zorder=1)
ax.plot(x, x / META["high_ratio_rp_over_rs"], color="#92979d", ls="--", lw=1.15, zorder=1)
for case in CASES:
    df = pd.read_csv(ROOT / f"launch_{case}.csv")
    ax.plot(df.secondary_rpm, df.primary_rpm, color=COLORS[case], label=case, zorder=2)
ax.set(xlim=(0, 4530), ylim=(0, 3990),
       xlabel="Secondary speed [rpm]", ylabel="Primary speed [rpm]")
ax.set_xticks(np.arange(0, 4001, 1000))
ax.set_yticks(np.arange(0, 3501, 500))
grid(ax)
ax.legend(loc="upper center", ncol=3, frameon=True,
          columnspacing=1.5, handlelength=2.0, borderaxespad=.4)
ann = dict(fontsize=8, color="#111111", ha="center", va="center",
           bbox=dict(facecolor="white", edgecolor="none", alpha=.9, pad=1.5),
           arrowprops=dict(arrowstyle="-", color="#111111", lw=.7))
ax.annotate("Low ratio", xy=(720, 720 / META["low_ratio_rp_over_rs"]),
            xytext=(800, 1225), **ann)
ax.annotate("High ratio", xy=(3470, 3470 / META["high_ratio_rp_over_rs"]),
            xytext=(3200, 930), **ann)
save(fig, "opening_free_shift_characteristics.png", 220)


# Mechanism panels.  Values are the same recovered mechanism/ramp maps as v4;
# the current manuscript wording calls panel (c) a contribution rather than a term.
fig, axs = plt.subplots(1, 3, figsize=(14.37, 5.26))
fig.subplots_adjust(left=.055, right=.993, bottom=.16, top=.93, wspace=.22)
for case in ["R00", "P300"]:
    df = pd.read_csv(ROOT / f"mechanism_{case}.csv")
    axs[0].plot(df.active_shift_fraction, df.primary_spring_opening_N,
                color=COLORS[case], label=case)
axs[0].set(title="(a) Spring opposition", xlabel="Active shift fraction",
           ylabel="Primary spring opening force [N]")
for case in ["R00", "RC10", "R26B7", "RC40L"]:
    ramp = pd.read_csv(ROOT / f"ramp_{case}.csv")
    mm = pd.read_csv(ROOT / f"mechanism_{case}.csv")
    axs[1].plot(ramp.ramp_coordinate_mm, ramp.radial_offset_mm,
                color=COLORS[case], label=case)
    axs[2].plot(mm.active_shift_fraction, mm.centrifugal_force_3000rpm_N,
                color=COLORS[case], label=case)
axs[1].set(title="(b) Ramp profile", xlabel="Physical ramp coordinate [mm]",
           ylabel="Radial ramp offset [mm]")
axs[2].set(title="(c) Closing contribution at 3000 rpm", xlabel="Active shift fraction",
           ylabel="Centrifugal closing contribution [N]")
for xval, yval in [(10, 24.0), (18, 20.8)]:
    axs[1].axvline(xval, color="#a5bed1", lw=.7, ls="--")
    axs[1].text(xval + .3, yval, f"{xval} mm", fontsize=7, color="#555555")
for ax in axs:
    grid(ax)
    ax.legend(loc="upper left", fontsize=7, framealpha=.9,
              borderpad=.35, labelspacing=.3)
for ax in [axs[0], axs[2]]:
    ax.set_xticks([0, .2, .4, .6, .8, 1.0])
save(fig, "shift_curve_mechanical_causes.png", 300)


# Analytic common road.  Dotted lines mark the named region boundaries only;
# they do not alter the road values.
course = pd.read_csv(ROOT / "course_profile.csv")
fig, ax = plt.subplots(figsize=(11.22, 5.05))
fig.subplots_adjust(left=.075, right=.992, bottom=.14, top=.975)
ax.plot(course.distance_m, course.grade_deg, color=COLORS["R00"], lw=1.45)
ax.set(xlim=(0, 732), ylim=(-36, 47),
       xlabel="Distance along road [m]", ylabel="Road grade [deg]")
grid(ax)
for value in [120, 224, 264, 336, 348, 604, 624, 708]:
    ax.axvline(value, color="#5aa9d6", ls=":", lw=.75, zorder=0)
for x0, label in [
    (60, "Opening flat"),
    (172, r"38$^\circ$ severe climb"),
    (300, "Six-cycle grade loading"),
    (476, r"18$^\circ$ sustained climb"),
    (666, r"−22$^\circ$ descent"),
]:
    ax.text(x0, 45.2, label, ha="center", va="top", fontsize=9)
for x0, label in [(244, "level\nrecovery"), (342, "level"),
                  (616, "level\nrecovery"), (720, "finish")]:
    ax.text(x0, 5.0 if x0 != 720 else 4.0, label,
            ha="center", va="center", fontsize=8)
save(fig, "common_course_profile.png", 220)
