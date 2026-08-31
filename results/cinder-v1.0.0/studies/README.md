# CINDER 1.0.0 studies

Each study derives from a frozen document in `../defaults/` and records only
its intentional changes in `study.json`.

Recommended layout:

```text
study-name/
├── README.md
├── study.json
├── run.py
├── artifacts/
└── work/
```

`run.py` should:

1. verify the release environment;
2. load the named baseline;
3. apply only the declared study overrides;
4. validate through `cinder.contracts`;
5. run CINDER;
6. save the fully resolved simulation document;
7. save machine-readable result data;
8. generate the study's plots/tables.

This makes the baseline tune common and reviewable while leaving each result
with a complete record of the exact input it executed.
