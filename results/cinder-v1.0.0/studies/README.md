# CINDER 1.0.0 studies

Create one subdirectory per independent result study or tightly related result
family.

Recommended minimal layout:

```text
study-name/
├── README.md
├── run.py
├── inputs/
└── artifacts/
```

Use a study-local `work/` directory for temporary or exploratory files;
`work/` is ignored by Git.

Every study must run from the CINDER 1.0.0 result virtual environment and
import `cinder` from the published `cinder-cvt==1.0.0` installation.
