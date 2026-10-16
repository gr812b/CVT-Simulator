# Flyweight and clamping formulations

These are the physical formulations for the common centrifugal-mechanism
boundary and the two supported clamping mechanisms. Software/API documentation
remains in [`cvtModel/docs/`](../../cvtModel/docs/README.md).

| Formulation | PDF | LaTeX source |
| --- | --- | --- |
| Common four-quantity boundary, based on the accepted Revision 4 derivation | [Common boundary](common_boundary/formulation.pdf) | [Source](common_boundary/formulation.tex) |
| Fixed-pivot roller flyweights / weight-and-ramp mechanism | [Fixed-pivot mechanism](fixed_pivot/formulation.pdf) | [Source](fixed_pivot/formulation.tex) |
| Fixed-orientation sliding blocks / CVTech-style mechanism | [Sliding-block mechanism](sliding_block/formulation.pdf) | [Source](sliding_block/formulation.tex) |

Each document has its own subfolder, with `formulation.tex` and
`formulation.pdf` directly beside one another. Build all three with
`make -C docs/flyweight_mechanisms` from the repository root (TeX Live and
`latexmk`). Intermediate files stay in the ignored `.build/` folder;
`make clean` in this folder removes only those intermediates. Cross-document
PDF links expect this layout. Previous view uses the PDF reader's navigation
history.

The fixed-pivot `reference/` folder preserves the independent reconstruction
and historical v1.1.5 comparison record cited in its formulation. The optional
`--repo` comparison deliberately requires that old source. Current behavior is
covered by the package smoke tests, including the ten-second fixed-pivot
launch regression. The sliding-block profiles are synthetic, not measured
CVTech hardware or a hardware-capacity validation.

The implementation uses the same canonical force, shaft-torque and energy
boundary for both mechanisms. See the
[common-boundary API guide](../../cvtModel/docs/CENTRIFUGAL_INERTIA_BOUNDARY.md),
[sliding-block API guide](../../cvtModel/docs/SLIDING_BLOCK_FLYWEIGHT.md), and
[verification record](VERIFICATION.md) for implementation scope and checks.

These formulations are repository-level documents. CINDER's package
distributions retain software documentation and examples; they do not bundle
this root documentation folder.
