"""Reproduce the CINDER/Ballew numerical-stability envelope figure.

Uses only the archived convergence summary.  Ballew's 0.01 ms marker is the
order-of-magnitude fixed timestep reported in Ballew (2015), Sec. 3.8; it is
not treated as a directly comparable adaptive solver step or runtime result.
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "results" / "convergence" / "convergence_summary.csv"
OUTPUT_DIR = ROOT / "results" / "numerical_stability"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(SOURCE)
tight = df.loc[df["case"].eq("0.50 ms, tighter tol")].iloc[0]
metrics = {
    "Primary-speed RMSE": "primary_rpm_rmse",
    "Secondary-speed RMSE": "secondary_rpm_rmse",
    "Speed-ratio RMSE": "speed_ratio_rmse",
    "Clamp-force RMSE": "primary_force_rmse_n",
}
rows = []
for _, row in df.iterrows():
    for label, col in metrics.items():
        rows.append({
            "case": row["case"],
            "max_step_ms": row["max_step_ms"],
            "metric": label,
            "difference_pct": abs((row[col] - tight[col]) / tight[col]) * 100.0,
        })
plot_df = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(10.5, 6.2))
for metric, group in plot_df.groupby("metric", sort=False):
    normal = group[group["case"] != "0.50 ms, tighter tol"].sort_values("max_step_ms")
    ax.plot(normal["max_step_ms"], normal["difference_pct"], marker="o", label=metric)

ballew_step_ms = 0.01
ax.axvline(ballew_step_ms, linestyle="--", linewidth=1.5)
ax.text(
    ballew_step_ms * 1.08,
    2.3e-4,
    "Ballew reported fixed-step scale\n≈ 0.01 ms (10 μs)",
    rotation=90,
    va="top",
    ha="left",
)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(0.007, 1.25)
ax.set_xlabel("Maximum integration step allowed in CINDER (ms)")
ax.set_ylabel("Absolute change from tightest-run RMSE (%)")
ax.set_title("CINDER closed-loop numerical convergence across time-step scale")
ax.grid(True, which="both", alpha=0.25)
ax.legend(loc="upper left")
fig.text(
    0.5, 0.01,
    "CINDER uses adaptive LSODA; max_step is an upper bound, not a fixed step. "
    "Ballew marker is a reported fixed-step scale, not a wall-clock benchmark.",
    ha="center", va="bottom", fontsize=8.5, wrap=True,
)
fig.tight_layout(rect=(0, 0.065, 1, 1))
fig.savefig(OUTPUT_DIR / "numerical_stability_envelope.png", dpi=220, bbox_inches="tight")
