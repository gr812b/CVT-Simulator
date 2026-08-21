# Reference data

The Figure 41 and Figure 45 digitizations are now included.

## Benchmark-ready files

These are the files consumed by the benchmark code:

- `figure_45_primary_force.csv`
  - Figure 45, undamped primary axial force.
  - columns: `time_s,primary_axial_force_n`.
  - prepared from the raw WebPlotDigitizer export with only the A6 cleanup
    documented below.
- `figure_41_input_rpm.csv`
  - Figure 41 input/primary pulley speed.
  - columns: `time_s,input_rpm`.
- `figure_41_output_rpm.csv`
  - Figure 41 output/secondary pulley speed.
  - columns: `time_s,output_rpm`.

The Figure 41 traces intentionally remain on their own native digitized time
grids. They do not need to be resampled onto a common grid for comparison.

## Raw provenance

The exact thesis PDF used for the benchmark is archived under `source/`, including its SHA-256 and page map.

`digitization/` contains the original five files exactly as supplied from
WebPlotDigitizer/Automeris:

- three headerless CSV exports;
- two WebPlotDigitizer project JSON files;
- a README describing how to reopen the thesis PDF and verify the clicked
  points/calibration.

Do not edit the five source files in place.

Regenerate the benchmark-ready CSVs with:

```powershell
python launchTools/literature/ballew_2015/reference/prepare_reference_data.py
```

The preparation step is deliberately minimal:

1. add explicit headers;
2. preserve the native Figure 41 point sets;
3. average four exact duplicate Figure 45 time coordinates caused by
   near-vertical segments being clicked twice in the same pixel column;
4. prepend the Figure 45 force replay at `t=0` using a zero-order hold of the
   first visible force point at `t=0.095541... s`.

Step 4 is necessary because Figure 45 itself does not draw the force curve all
the way to zero time, while CINDER needs a prescribed input at the initial
state. It is Reconstruction A6 and should be treated as a small digitization
boundary assumption, not source data.

No smoothing, filtering, curve fitting, or controller reconstruction is
performed.

Source pages:

- Figure 41: printed p. 58 / PDF page 68.
- Figure 45: printed p. 62 / PDF page 72.

Table B1 remains authoritative for the exact initial shaft speeds (`2500 rpm`
and `1136 rpm`). The graph traces are comparison data over the interval where
the published curves are visible.

## Figure 45 has two benchmark roles

The digitization itself is single-source and unchanged, but it is used differently by the two comparison protocols:

- `run_comparison.py`: Figure 45 is the prescribed primary-force **input** for the force-replay plant comparison.
- `run_closed_loop_comparison.py`: Figure 45 is a primary-force **output reference** for the reconstructed Ballew controller.

The second protocol never feeds the Figure 45 values into the controller.
