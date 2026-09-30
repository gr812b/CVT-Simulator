"""Export helpers and the independent absolute-tolerance display for Results 4.2.3.

Canonical invocation: python studies/solver-convergence/run.py --plot-only
No contours or decision boundaries are inferred between sampled cells.
Continuous traces are drawn separately on each retained hybrid segment.
"""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

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
    # Finish serialization before replacing a publication asset. An interrupted
    # export must not leave a partial PDF at the manuscript's canonical path.
    for suffix in ('pdf', 'png'):
        buffer = BytesIO()
        options = {'metadata': {'CreationDate': None, 'ModDate': None}} if suffix == 'pdf' else {}
        fig.savefig(buffer, format=suffix, **options)
        content = buffer.getvalue()
        if suffix == 'pdf' and not content.rstrip().endswith(b'%%EOF'):
            raise ValueError(f'Incomplete PDF export: {name}')
        target = out / f'{name}.{suffix}'
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_bytes(content)
        temporary.replace(target)
    plt.close(fig)


def absolute_tolerance_panel(ax, atol, values, title="(d) Independent absolute-tolerance sweep"):
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
    ax.set(xscale="log", yscale="log", xlim=(1.7e-5, .6e-8), ylim=(8e-5, 7))
    ax.set_xticks(xs, [sci(x) for x in xs])
    ax.minorticks_off()
    ax.set_yticks([1e-4, 1e-2, 1], [r"$10^{-4}$", r"$10^{-2}$", "1"])
    ax.set_ylabel("Error / guard limit")
    ax.set_xlabel(r"Absolute tolerance at $\mathrm{rtol}=10^{-4}$ and 10 ms maximum step", labelpad=3)
    ax.set_title(title, loc="left", pad=24)
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(-.008, 1.005), frameon=False,
              borderaxespad=0, handletextpad=.3, columnspacing=1)
    ax.grid(axis="y", color="#eeeeee", lw=.5)
