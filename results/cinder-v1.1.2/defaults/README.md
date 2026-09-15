# CINDER v1.1.2 shared results defaults

This directory owns the reusable inputs and reference-model policy for the
CINDER 1.1.2 results programme.

```text
defaults/
├── baja/
│   ├── simulation_case.json
│   ├── tuning.json
│   ├── provenance.json
│   └── README.md
├── reference_model/
│   ├── __init__.py
│   ├── reference_case.py
│   ├── slotted_helix.py
│   ├── policy.json
│   └── README.md
└── verification/
    ├── operating_cases.json
    └── README.md
```

`baja/` owns frozen public CINDER input and provenance.
`reference_model/` owns the executable bilateral results interpretation.
`verification/` owns reusable operating-state/search recipes. Individual studies
retain their own guards, metrics and PASS/REVIEW/FAIL semantics.
