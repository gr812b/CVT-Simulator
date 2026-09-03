# Ballew reference data

This directory contains both the **raw digitization provenance** and the
**benchmark-ready reference traces** consumed by the study.

## Benchmark-ready files

- `figure_41_input_rpm.csv`
  - Figure 41 input/primary pulley speed.
  - columns: `time_s,input_rpm`.
- `figure_41_output_rpm.csv`
  - Figure 41 output/secondary pulley speed.
  - columns: `time_s,output_rpm`.
- `figure_45_primary_force.csv`
  - Figure 45 undamped primary axial force.
  - columns: `time_s,primary_axial_force_n`.

The Figure 41 traces intentionally remain on their own native digitized time
grids. The benchmark does not resample them onto a common grid before computing
the individual speed errors.

## Raw provenance

`digitization/` contains the immutable WebPlotDigitizer source bundle:

- `input_rpm.csv`
- `output_rpm.csv`
- `axial_force.csv`
- `rpms_ballew.json`
- `axial_force_ballew.json`

`source/Ballew_2015_thesis.pdf` is the exact thesis PDF used for the
digitization and reconstruction.

Do not edit the raw digitization files in place.

## Regenerating the prepared traces

From the study directory:

```powershell
python reference/prepare_reference_data.py
python reference/prepare_reference_data.py --check
```

`--check` verifies that the committed benchmark-ready files are exactly
reproducible from the raw digitization without modifying them.

The preparation is deliberately minimal:

1. add explicit headers;
2. preserve the native Figure 41 point sets independently;
3. average the four exact duplicate Figure 45 time coordinates caused by
   near-vertical segments being clicked twice in the same pixel column;
4. prepend Figure 45 at `t=0` using a zero-order hold of the first visible force
   point (`t≈0.095541 s`) so force replay has an input at the initial state.

Step 4 is Reconstruction A6. It is an explicit boundary assumption, not source
data. No smoothing, filtering, curve fitting, or resampling is performed.

## Figure 45 has two roles

The digitization itself is single-source and unchanged:

- **force replay:** Figure 45 is the prescribed primary-clamp input;
- **closed loop:** Figure 45 is an output reference only and is never fed into
  the reconstructed controller.
