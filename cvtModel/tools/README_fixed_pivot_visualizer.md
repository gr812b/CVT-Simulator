# PR #474 fixed-pivot branch-tracking visualizer

This ZIP **supersedes the earlier provisional visualizer ZIP**.

It targets PR #474 / branch `flyweight-force-fix` and is intentionally a
visual-verification step before changing the production runtime map's contact
branch semantics.

## Apply

From the repository root:

```bash
python apply_pr474_fixed_pivot_visualizer.py
```

Then:

```bash
cd cvtModel
PYTHONPATH=src python tools/visualize_fixed_pivot_flyweight.py
```

## What changed from the first viewer

The viewer now distinguishes:

1. all instantaneous mathematical arm/roller/ramp contact configurations; and
2. the one branch physically reachable from the installed arm-in state.

At fully open, the viewer starts the free arm at `q = -45 deg` and searches in
increasing `q` until first contact. From there it follows the nearest continuous
contact branch as closure increases. Alternate mathematical configurations are
still drawn faintly, but are not treated as configurations the hardware can
teleport into.

This is the key conceptual distinction between **multiple mathematical roots**
and **simultaneous physical double contact**.

The production PR #474 constructor has **not yet been converted** to this branch
selection rule in this step. The point of this viewer is to verify the measured
geometry and branch first, then promote the same construction-time branch trace
into the production `q_f(x)` compiler.

If the earlier provisional ZIP was already applied, this apply script removes
the extra global "all roots must remain unique" validation that earlier ZIP
added. That stricter rule is no longer appropriate under the clarified branch
interpretation.

## Drawing changes

The mechanism plot now labels and shows:

- `O`: shaft centre;
- `P`: fixed flyweight pivot;
- `A`: physical start/tip of the ramp;
- the measured shaft-to-pivot radius `r_P`;
- the dashed installed arm-in pose at `q = -45 deg`;
- the physical ramp;
- all mathematical candidate arms/rollers faintly;
- the history-selected reachable arm/roller prominently;
- selected contact `C`.

All numeric/status text was moved to a separate side panel so it no longer sits
on top of the mechanism drawing.

The `q_f` plot shows the raw mathematical contact roots as points and the
history-selected branch as a continuous line.

## Temporary Point A change

The measured axial estimate was `0.2776 in`. Per the latest request, the viewer
temporarily adds `+0.1000 in` in the model's positive axial direction:

- measured estimate: `0.2776 in`
- temporary addition: `+0.1000 in`
- effective viewer value: `0.3776 in`

The radial estimate remains `1.4685 in`.

This makes the temporary effective `|PA|` about `1.51627 in` (`38.513 mm`).
The JSON keeps both the measured and temporary-adjusted numbers explicitly so
the extra 0.1 in cannot be mistaken for a measured dimension.

## Important terminology

A second mathematical root means another *possible arm orientation* satisfying
the static contact geometry. It is not automatically a second simultaneous
contact on the already-selected roller pose.

Actual physical double contact/interference still means one selected roller
configuration touches/penetrates another part of the physical ramp; that
remains something the mechanism must reject.
