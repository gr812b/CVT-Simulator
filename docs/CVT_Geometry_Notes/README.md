# Supplementary CVT Geometry Notes

This directory contains the two geometry appendices removed from the main
`CVT_Module_Formulation` manuscript:

1. the updated small-angle belt-length approximation study; and
2. the geometric CVT ratio rate/acceleration and design-map material.

## Install

Extract the supplied ZIP over the repository root. It creates only:

```text
docs/
└── CVT_Geometry_Notes/
    ├── CVT_Geometry_Notes.tex
    ├── cvt_geometry_note_calculations.py
    ├── copy_figures.py
    └── README.md
```

The figures are intentionally not duplicated in the ZIP.

## Copy the figures

From anywhere in the repository:

```bash
python docs/CVT_Geometry_Notes/copy_figures.py
```

This copies the six required figures from:

```text
docs/CVT_Module_Formulation/figures/appendix/cvt_ratio_rate/
```

to:

```text
docs/CVT_Geometry_Notes/figures/
```

The script checks that all required source figures exist before copying any
files, and it is safe to run again after the source figures change.

## Recompute the approximation numbers

```bash
python docs/CVT_Geometry_Notes/cvt_geometry_note_calculations.py
```

The script uses only the Python standard library.

## Compile

For external equation/section numbers to resolve, compile the main formulation
first so that `CVT_Module_Formulation.aux` exists. Then either compile from this
directory:

```bash
cd docs/CVT_Geometry_Notes
pdflatex CVT_Geometry_Notes.tex
bibtex CVT_Geometry_Notes
pdflatex CVT_Geometry_Notes.tex
pdflatex CVT_Geometry_Notes.tex
```

or use `latexmk -cd` from the repository root if available:

```bash
latexmk -pdf -cd docs/CVT_Geometry_Notes/CVT_Geometry_Notes.tex
```

If the main formulation `.aux` file is absent, the note still compiles; the
`\FormEq{...}` and `\FormSec{...}` helpers display the formulation label names
instead of numbered external references.
