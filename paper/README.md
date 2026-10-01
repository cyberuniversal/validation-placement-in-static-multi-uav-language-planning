# IEEE Manuscript

This directory is the self-contained submission package.

- `main.tex`: editable IEEE conference manuscript.
- `main.pdf`: compiled manuscript.
- `figures/`: figures used by the manuscript.
- `data/multiuav_resource_contrasts_v1.csv`: frozen source table for the
  compact resource figure.
- `build_resource_figure.py`: deterministic resource-figure generator.
- `figures/accuracy_refusal_aware_outcomes_v2.*`: reviewer-revised primary
  outcome figure with a labeled always-BLOCK reference.

Build from this directory:

```powershell
python build_resource_figure.py
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The manuscript reports static plan fidelity and post-hoc validator diagnostics.
It does not report official simulator execution or physical-flight results.

The separate anonymous NeurIPS 2026 package is under
`neurips_2026_anonymous/`. It uses the official annual style and includes the
required checklist without changing the frozen scientific results.

