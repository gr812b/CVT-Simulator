# Ballew 2015 reference package

This directory is the permanent results-tree home for the benchmark's source
material and digitization. It is intentionally not a runtime link back to
`cvtModel/launchTools`.

Already bundled in the drop-in:

- `source/Ballew_2015_thesis.pdf` — exact thesis used by the legacy benchmark;
- `.legacy-lfs-pointers/` — provenance for the three prepared comparison CSVs;
- `digitization/README.md` — digitization inventory and preparation rules.

Materialized from the frozen `cinder-v1.0.0` tag by `../migrate_legacy.py`:

```text
reference/
├── figure_41_input_rpm.csv
├── figure_41_output_rpm.csv
├── figure_45_primary_force.csv
├── prepare_reference_data.py
├── digitization/
│   ├── README.md
│   ├── input_rpm.csv
│   ├── output_rpm.csv
│   ├── axial_force.csv
│   ├── rpms_ballew.json
│   └── axial_force_ballew.json
└── source/
    ├── Ballew_2015_thesis.pdf
    └── README.md
```

The migration verifies every Git-LFS object against its pointer SHA-256 and
records the complete source/target integrity mapping under
`provenance/migration_manifest.json`.

Source page map:

- Figure 39: printed p. 54 / PDF p. 64;
- Figure 41: printed p. 58 / PDF p. 68;
- Figure 45: printed p. 62 / PDF p. 72;
- Table A1: printed p. 69 / PDF p. 79;
- Table B1: printed p. 70 / PDF p. 80.
