"""Rebuild the accepted two-panel figure with its linked engine-power curve.

No simulation, smoothing or fitted equilibrium curve. Event/checkpoint segment
boundaries remain broken; only the two road-window endpoints are interpolated.
"""
from pathlib import Path
import io
import json
import platform
import numpy as np
import course_csvframe as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from engine_power import engine_curve

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "figures/results/course"
OUT.mkdir(parents=True, exist_ok=True)
CASES = ("R00", "W85", "H28", "RC40L", "D01", "D02_P")
COL = {"R00": "#286A9A", "W85": "#A83F78", "H28": "#438D98",
       "RC40L": "#7160B4", "D01": "#BF7025", "D02_P": "#238371"}
STYLE = {"R00": "-", "W85": "-", "H28": (0, (4, 1.8)),
         "RC40L": (0, (5.5, 3)), "D01": "-", "D02_P": "-"}
audit = json.loads((HERE / "moderate_evidence.json").read_text())
spec = json.loads((HERE / "engine_boundary.json").read_text())
power = engine_curve(spec)
means = {c: audit["cases"][c]["tail_means"] for c in CASES}
for c in CASES:
    # Mark the power at the mean RPM; do not claim this is exactly the mean
    # power. The two agree at the table's 0.01 kW reporting precision.
    assert f"{float(power(means[c]['primary_rpm'])):.2f}" == f"{means[c]['primary_boundary_power_W']/1000:.2f}"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
    "axes.titlesize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .7, "lines.linewidth": 1.5, "axes.axisbelow": True,
    "legend.frameon": False, "savefig.facecolor": "white", "pdf.fonttype": 42,
    "svg.fonttype": "none",
})
fig = plt.figure(figsize=(7.6, 4.25))
upper = fig.add_axes([.095, .595, .702, .325])
lower = fig.add_axes([.095, .14, .702, .325], sharex=upper)
axs = [upper, lower]
for ax in axs:
    ax.set_xlim(0, 38)
    ax.set_xticks(np.arange(0, 36, 5))
    ax.grid(axis="y", color="#d6d8dc", alpha=.65, lw=.5)
upper.tick_params(labelbottom=False)

for cid in CASES:
    d = pd.read_csv(HERE / f"{cid}_moderate.csv")
    q = d[d.distance_m.between(348, 596)]
    assert q.contact_mode.eq("stick_stick").all()
    ev = audit["cases"][cid]
    t0 = ev["entry"]["time_s"]
    for ax, key in zip(axs, ("shift_mm", "primary_rpm")):
        ts, ys = [0.0], [ev["entry"][key]]
        previous = None
        for row in q.itertuples(index=False):
            if previous is not None and previous != row.segment_id:
                ts.append(np.nan)
                ys.append(np.nan)
            ts.append(row.time_s - t0)
            ys.append(getattr(row, key))
            previous = row.segment_id
        ts.append(ev["hold_exit"]["time_s"] - t0)
        ys.append(ev["hold_exit"][key])
        ax.plot(ts, ys, color=COL[cid], ls=STYLE[cid], lw=1.6,
                zorder=5 if cid == "RC40L" else 3)

low, high = audit["cases"]["R00"]["stops_mm"]
axs[0].axhline(high, color="#737c82", ls=(0, (2.4, 2.8)), lw=.8, zorder=1)
axs[0].axhline(low, color="#737c82", ls=(0, (2.4, 2.8)), lw=.8, zorder=1)
axs[0].set_ylim(1.1, 21.3)
axs[0].set_yticks([5, 10, 15, 19.05], labels=["5", "10", "15", "19.05"])
axs[0].set_ylabel("Shift [mm]")
axs[0].set_title("(a) Backshift and the approach to interior operation", loc="left", pad=6)
axs[0].text(37.5, high + .45, "Upper primary stop", ha="right", fontsize=7.7, color="#626b72")
axs[0].text(37.5, low + .55, "Low-ratio seat", ha="right", fontsize=7.7, color="#626b72")
axs[1].set_ylim(2220, 3930)
axs[1].set_yticks([2400, 2800, 3200, 3600])
axs[1].set_ylabel("Primary speed [rpm]")
axs[1].set_xlabel("Time since each vehicle reaches 348 m [s]")
axs[1].set_title("(b) Engine speed during the climb", loc="left", pad=6)
handles = [Line2D([0], [0], color=COL[c], ls=STYLE[c], lw=1.7, label=c) for c in CASES]
legend_ax = fig.add_axes([.847, .595, .135, .325])
legend_ax.set_axis_off()
legend = legend_ax.legend(handles=handles, loc="center", ncol=1,
                          fontsize=8.3, handlelength=2.2, handletextpad=.7,
                          labelspacing=.72, borderpad=0, borderaxespad=0)
profile = fig.add_axes([.847, .14, .135, .325], sharey=lower)
rpm = np.linspace(2220, 3930, 1200)
profile.plot(power(rpm), rpm, color="#59636c", lw=1.35)
profile.set_xlim(0, 8)
profile.set_xticks([0, 4, 8])
profile.tick_params(axis="y", left=False, labelleft=False)
profile.spines["left"].set_visible(False)
profile.spines["bottom"].set_color("#91999f")
profile.set_xlabel("Power [kW]", fontsize=8.2, labelpad=5)
profile.set_title("Engine\ncharacteristic", fontsize=8, pad=5)
for c in CASES:
    rpm_c = means[c]["primary_rpm"]
    profile.plot(float(power(rpm_c)), rpm_c, "o", ms=4.0 if c != "RC40L" else 5.8,
                 mec=COL[c], mfc=COL[c] if c != "RC40L" else "none",
                 mew=.9, zorder=5)
fig.canvas.draw()
legend_box = legend.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
assert legend_box.x0 >= .84 and legend_box.x1 <= .99
assert legend_box.y0 >= .595 and legend_box.y1 <= .92
assert np.allclose(upper.get_position().extents[[0, 2]], lower.get_position().extents[[0, 2]])
assert np.allclose(profile.get_position().extents[[1, 3]], lower.get_position().extents[[1, 3]])
for suffix in ("png", "pdf", "svg"):
    buffer = io.BytesIO()
    fig.savefig(buffer, format=suffix, dpi=300)
    payload = buffer.getvalue()
    destination = OUT / f"moderate_hill_operating_conditions.{suffix}"
    destination.write_bytes(payload)
    assert destination.read_bytes() == payload
    if suffix == "png":
        from PIL import Image
        Image.open(destination).verify()
    elif suffix == "pdf":
        from course_pdfcheck import PdfReader
        assert len(PdfReader(destination, strict=True).pages) == 1
    else:
        from xml.etree import ElementTree
        ElementTree.parse(destination)
plt.close(fig)
(HERE / "figure_build.json").write_text(json.dumps({
    "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
    "matplotlib": matplotlib.__version__, "cases": CASES, "road_window_m": [348, 596],
    "hold_window_m": [356, 596], "size_inches": [7.6, 4.25], "png_dpi": 300,
    "alignment": "Each recorded history shifted in time by its interpolated 348 m crossing",
    "segments": "Breaks retained; endpoints interpolated only within continuous segments",
    "overlap": "RC40L dashed over R00; their late traces coincide at this scale",
    "power_curve": "Supplied torque PCHIP times angular speed, sharing the primary RPM ordinate",
    "markers": "Power evaluated at each late mean primary RPM; R00 dot with RC40L open ring",
    "power_at_mean_vs_mean_power": "Agreement at the table's 0.01 kW precision for all six cases",
    "layout_checks": "Main time axes aligned; RPM and power curve vertically aligned; legend fits upper-right column",
}, indent=2) + "\n")
print("Saved moderate_hill_operating_conditions.png, .pdf and .svg")
