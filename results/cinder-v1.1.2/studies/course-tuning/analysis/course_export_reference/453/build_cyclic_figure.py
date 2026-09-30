"""Rebuild the manuscript figure from included production diagnostic excerpts.

Requires NumPy, pandas and Matplotlib. No re-integration, smoothing, resampling,
force extrapolation or fitted damping curve is used.
"""
from pathlib import Path
import json
import platform
import numpy as np
import course_csvframe as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "figures/results/course"
OUT.mkdir(parents=True, exist_ok=True)
COL = {"R26B7": "#7160B4", "R00": "#286A9A", "P300": "#238371", "RC10": "#BD3F46"}
STYLE = {"R26B7": (0, (1.0, 2.4)), "R00": "-", "P300": (0, (5, 2.5)), "RC10": "-"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
    "axes.titlesize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .7, "lines.linewidth": 1.5, "axes.axisbelow": True,
    "legend.frameon": False, "savefig.facecolor": "white", "pdf.fonttype": 42,
})
data = {c: pd.read_csv(HERE / f"{c}_cyclic.csv") for c in COL}
road = pd.read_csv(HERE / "cyclic_course_profile.csv")
fig, axs = plt.subplots(3, 1, figsize=(6.5, 4.65), sharex=True,
                        gridspec_kw={"height_ratios": [.85, 1.6, 1.45]})
fig.subplots_adjust(left=.115, right=.982, top=.91, bottom=.10, hspace=.38)

for ax in axs:
    ax.set_xlim(264, 336)
    ax.set_xticks(np.arange(264, 337, 12))
    ax.grid(axis="y", color="#d6d8dc", alpha=.65, lw=.5)
    for x in np.arange(276, 336, 12):
        ax.axvline(x, color="#c3c8cd", ls=(0, (2, 3)), lw=.6, zorder=0)
    ax.axvspan(264, 270, color="#eef0f2", zorder=0)
    ax.axvspan(330, 336, color="#eef0f2", zorder=0)

q = road[road.distance_m.between(264, 336)]
axs[0].plot(q.distance_m, q.grade_deg, color="#303940", lw=1.35)
axs[0].set_ylim(-39, 47)
axs[0].set_yticks([-32, 0, 32])
axs[0].set_ylabel("Grade [deg]")
axs[0].set_title("(a) Repeated longitudinal loading", loc="left", pad=5)
for cycle, x in enumerate(np.arange(270, 336, 12), 1):
    axs[0].text(x, 40, str(cycle), ha="center", va="center", fontsize=8, color="#626b72")

axs[1].axhline(19.05, color="#777f85", lw=.8, ls=(0, (3, 3)), zorder=.5)
# Plot styles preserve identification where supported traces share one ordinate.
for c in ("R00", "P300", "R26B7", "RC10"):
    d = data[c]
    w = d[d.distance_m.between(264, 336)]
    assert w.contact_mode.eq("stick_stick").all()
    axs[1].plot(w.distance_m, w.shift_mm, color=COL[c], ls=STYLE[c],
                lw=1.6 if c != "R26B7" else 1.9)
    # Zero outside contact is the actual absence of a hardware support force,
    # not an estimate of the reaction an artificially constrained solve needs.
    reaction = np.where(w.shift_constraint.eq("upper_stop"), w.upper_stop_reaction_N, 0.0)
    assert np.isfinite(reaction).all()
    axs[2].plot(w.distance_m, reaction / 1000, color=COL[c], ls=STYLE[c],
                lw=1.6 if c != "R26B7" else 1.9)
    events = json.loads((HERE / f"{c}_events.json").read_text())
    for e in events:
        if "released" in e["reason"] and 264 <= e["distance_m"] <= 336:
            axs[2].plot(e["distance_m"], 0, "o", ms=4, mfc="white", mec=COL[c], mew=1.1, zorder=8)

axs[1].set_ylim(15.5, 19.72)
axs[1].set_yticks([16, 17, 18, 19.05], labels=["16", "17", "18", "19.05"])
axs[1].set_ylabel("Shift [mm]")
axs[1].set_title("(b) Shift motion and the common upper stop", loc="left", pad=5)
axs[1].text(300, 19.37, "Upper primary stop", color="#626b72", fontsize=8)
axs[2].set_ylim(-.10, 3.8)
axs[2].set_yticks([0, 1, 2, 3])
axs[2].set_ylabel("Stop reaction [kN]")
axs[2].set_xlabel("Road position [m]")
axs[2].set_title("(c) Primary closing load carried by the stop", loc="left", pad=5)

handles = [Line2D([0], [0], color=COL[c], ls=STYLE[c], lw=1.7, label=c) for c in COL]
fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.55, 1.006),
           ncol=4, columnspacing=1.9, handlelength=3.2)
for suffix in ("png", "pdf"):
    fig.savefig(OUT / f"cyclic_shift_and_support.{suffix}", dpi=300)
plt.close(fig)
(HERE / "figure_build.json").write_text(json.dumps({
    "python": platform.python_version(), "numpy": np.__version__,
    "pandas": pd.__version__, "matplotlib": matplotlib.__version__,
    "plot_window_m": [264, 336], "cases": list(COL),
    "source": "Saved production excerpts; no simulation rerun",
    "free_mode_reaction": "Zero actual support force; not a free-mode required reaction",
    "release_markers": "Exact events.json distance; not sampled threshold detection",
    "output_size_inches": [6.5, 4.65], "png_dpi": 300,
}, indent=2) + "\n")
print("Saved cyclic_shift_and_support.png and .pdf")
