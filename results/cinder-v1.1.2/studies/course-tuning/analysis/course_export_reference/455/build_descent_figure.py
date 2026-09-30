"""Rebuild the single-panel figure from the included R00 diagnostic excerpt."""
from pathlib import Path
import io
import json
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import course_csvframe as pd
from PIL import Image
from course_pdfcheck import PdfReader

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "figures/results/course"
OUT.mkdir(parents=True, exist_ok=True)
d = pd.read_csv(HERE / "R00_descent.csv")
audit = json.loads((HERE / "descent_evidence.json").read_text())
assert d.contact_mode.eq("stick_stick").all()
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .7, "axes.axisbelow": True, "legend.frameon": False,
    "savefig.facecolor": "white", "pdf.fonttype": 42,
})
fig, ax = plt.subplots(figsize=(6.5, 2.35))
fig.subplots_adjust(left=.11, right=.983, top=.825, bottom=.17)
ax.set_xlim(604, 732)
ax.set_ylim(-13, 23)
ax.set_xticks([604, 624, 636, 660, 680, 696, 708, 732])
ax.set_yticks([-10, -5, 0, 5, 10, 15, 20])
ax.axvspan(624, 708, color="#eef0f2", zorder=0)
ax.axvspan(636, 696, color="#dfe3e7", zorder=0)
ax.grid(axis="y", lw=.5, color="#cbd0d5", alpha=.7)
ax.axhline(0, color="#5d6269", lw=.9, zorder=2)
curves = (
    ("primary_boundary_power_W", "#286A9A", "-", "Engine boundary (primary)"),
    ("secondary_boundary_power_W", "#BF7025", (0, (5, 2)), "Net road load (secondary)"),
)
for field, color, style, label in curves:
    # Each continuous solver segment is drawn separately, including the paired
    # predecessor/successor rows at the upper-stop impact. No smoothing.
    for _, group in d.groupby("segment_id", sort=False):
        ax.plot(group.distance_m, group[field] / 1000, color=color, ls=style,
                lw=1.7, zorder=4)
for start, end, label in ((604, 624, "Level"), (624, 636, "Entry"),
                          (636, 696, r"$-22^\circ$ hold"), (696, 708, "Exit"),
                          (708, 732, "Level")):
    ax.text((start + end) / 2, 21.1, label, ha="center", va="center",
            color="#5b6269", fontsize=7.5)
ax.set_xlabel("Road distance [m]")
ax.set_ylabel("Boundary power [kW]")
fig.legend(handles=[Line2D([0], [0], color=c, ls=s, lw=1.7, label=l)
                    for _, c, s, l in curves], loc="upper center",
           bbox_to_anchor=(.54, 1.01), ncol=2, columnspacing=2.0, handlelength=3.1)
for suffix in ("png", "pdf"):
    buffer = io.BytesIO()
    fig.savefig(buffer, format=suffix, dpi=300)
    payload = buffer.getvalue()
    path = OUT / f"descent_reverse_power.{suffix}"
    path.write_bytes(payload)
    assert path.read_bytes() == payload
    if suffix == "png":
        Image.open(path).verify()
    else:
        assert len(PdfReader(path, strict=True).pages) == 1
plt.close(fig)
(HERE / "figure_build.json").write_text(json.dumps({
    "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
    "matplotlib": matplotlib.__version__, "case": "R00", "road_window_m": [604, 732],
    "descent_window_m": [624, 708], "constant_grade_window_m": [636, 696],
    "size_inches": [6.5, 2.35], "png_dpi": 300,
    "signs": audit["power_sign_convention"],
    "data_policy": "Chronological diagnostics, continuous segments drawn separately; no smoothing or fitted curve. Viewport clips at 604 m; all original segment endpoints retained.",
}, indent=2) + "\n")
print("Saved descent_reverse_power.png and .pdf")
