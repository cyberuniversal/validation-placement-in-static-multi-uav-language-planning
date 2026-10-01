# CoRL 2026 SPAIS Anonymous Submission

This directory contains the double-blind, four-page workshop version prepared
for the Science of Physical AI Safety workshop at CoRL 2026. It uses the
official CoRL 2026 submission style and preserves the revised study claims.

Build from this directory:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The content-page limit is four pages excluding references. The initial
submission is anonymized by `corl_2026.sty`; do not enable the `final` or
`preprint` option before review.
