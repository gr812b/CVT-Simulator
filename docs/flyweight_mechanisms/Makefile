# Keep all LaTeX auxiliaries in .build; only sources and final PDFs are tracked.
SHELL := /bin/sh
DOCUMENTS := common_boundary fixed_pivot sliding_block
.PHONY: all clean $(DOCUMENTS)
all: $(DOCUMENTS)
$(DOCUMENTS):
	mkdir -p .build/$@
	latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(CURDIR)/.build/$@ $@/formulation.tex
	cp .build/$@/formulation.pdf $@/formulation.pdf
clean:
	rm -rf .build
