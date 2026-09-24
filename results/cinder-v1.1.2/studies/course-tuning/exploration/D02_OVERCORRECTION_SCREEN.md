# D02 flyweight over-correction screen

This exploratory screen is the selection evidence for the final `D02_M150` diagnostic. It remains separate from the root final runner: the final case is now defined independently in `inputs/competitors.json` and is regenerated from the common initial state when the final study is run.

## Question

Starting from `D02_M` (reference tip mass with D02's 115% primary preload), how far can primary centrifugal actuation be increased before the severe 38-degree hill response changes from a useful traction repair into insufficient backshift?

The screen keeps D02's primary preload at 115% and changes only replaceable flyweight tip mass. The existing Results tuning resolver updates the corresponding flyweight total mass, first moment, and second moment consistently.

Cases:

- `D02`: 65% tip, 115% primary preload — original adverse anchor
- `D02_P`: 65% tip, 100% preload — preload-repair anchor
- `D02_M`: 100% tip, 115% preload — mass-repair anchor
- `D02_M110`: 110% tip, 115% preload
- `D02_M120`: 120% tip, 115% preload
- `D02_M130`: 130% tip, 115% preload
- `D02_M140`: 140% tip, 115% preload
- `D02_M150`: 150% tip, 115% preload

## Frozen-environment result

Campaign `unified38_c6a32w12_h18hold240__tight__a625698e273b` used the frozen manuscript environment (Python 3.12.4, CINDER 1.1.2, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1). D02 reproduced its progress-limited failure. Every repair/over-repair case completed the 732 m course with zero inspection errors and no sampled review flag.

The 100-140% mass-repair cases reached and retained the low-ratio seat during the main 38-degree hold. `D02_M150` was the first tested point in the 100-150% sequence to cross the qualitative boundary: it reached the low-ratio seat near 171.132 m, then released it near 173.041 m with `low_ratio_seat_released_by_tensile_reaction` and returned to free shift. It is therefore the selected high-primary-force over-correction diagnostic in the final fleet.

This selection does not turn that outcome into a required result. The root final runner starts `D02_M150` from the same common initial state as every other selected case and records whatever trajectory the fixed model produces.

## Reproduce the screen

From `results/cinder-v1.1.2` in the frozen Results environment, PowerShell users can run:

```powershell
python studies/course-tuning/exploration/run.py --course studies/course-tuning/inputs/course.json --competitors studies/course-tuning/exploration/inputs/d02_overcorrection.json --preset tight --cars D02 D02_P D02_M D02_M110 D02_M120 D02_M130 D02_M140 D02_M150 --jobs 4 --resume --focus D02 D02_P D02_M D02_M110 D02_M120 D02_M130 D02_M140 D02_M150
```
