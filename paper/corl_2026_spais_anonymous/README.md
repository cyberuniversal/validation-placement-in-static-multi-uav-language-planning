# CoRL 2026 LEAP Revision

This directory now contains the anonymous LEAP revision in official CoRL 2026
style. The directory name is historical. The PDF has six pages total, including
references and a one-page appendix, and must be submitted as a long paper,
not the previous four-page SPAIS short paper. LEAP allows up to eight content
pages plus unlimited references and appendices.

Title: Failure Containment and Executable Actions in Language-Based Multi-UAV
Planning.

The frozen M1-M4 results remain unchanged. A new, explicitly separate section
reports the inspected 15-mission training-split development cohort: six official
task-check successes, three terminal false checks, five CUDA memory failures,
and one deadline interruption. Two cases guided repair. These counts are not
held-out accuracy, a fifth M1-M4 condition, a matched placement comparison, or
physical UAV execution. The appendix lists every task/session and immutable
execution bindings.

Build from this directory:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The submission remains anonymized by `corl_2026.sty`. The separate IEEE paper
and previously submitted copies are not overwritten. This revision is not
automatically submitted to OpenReview.
