# Ballew digitization provenance

This is the **new home** of the exact Figure 41 / Figure 45 digitization package.
Run `../migrate_legacy.py` once after unzipping the drop-in into the repository;
it copies the original assets from the frozen `cinder-v1.0.0` tag into this
directory and verifies them.

The migrated directory contains the same five raw WebPlotDigitizer source files
as the legacy benchmark:

- `input_rpm.csv` — raw headerless Figure 41 input-RPM clicks;
- `output_rpm.csv` — raw headerless Figure 41 output-RPM clicks;
- `axial_force.csv` — raw headerless Figure 45 axial-force clicks;
- `rpms_ballew.json` — WebPlotDigitizer project for Figure 41;
- `axial_force_ballew.json` — WebPlotDigitizer project for Figure 45.

Those five source files must not be edited in place. The exact legacy
`prepare_reference_data.py` is also migrated to `reference/`; it creates the
benchmark-ready files:

- `figure_41_input_rpm.csv` (`time_s,input_rpm`);
- `figure_41_output_rpm.csv` (`time_s,output_rpm`);
- `figure_45_primary_force.csv` (`time_s,primary_axial_force_n`).

### Digitization sanity checks

- input RPM: 113 points, visible `t ~= 0.110375–4.988962 s`;
- output RPM: 64 points on its own native time grid over the same visible range;
- axial force: 211 raw clicked points, visible `t ~= 0.095541–5.0 s`;
- Figure 45 contains four exact duplicate time coordinates from near-vertical
  clicked segments; the prepared data averages those duplicates;
- the first visible Figure 45 force is held backward to `t=0` only for the
  force-replay boundary input.

No smoothing, filtering, curve fitting, or resampling is part of preparation.

The three prepared CSV Git-LFS OIDs are preserved in
`reference/.legacy-lfs-pointers/` even before hydration. The thesis PDF itself is
already bundled under `reference/source/` and has SHA-256
`cafead74895bbfaf092fe0354f0572064f44c6b4ff10c422877c5ae587f8df44`.
