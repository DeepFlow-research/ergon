# Frontend Quality RFC Assets

These images support
`../README.md`.

The chat attachment binaries are not directly available to Codex as files, so
these assets are local equivalents. Treat the files in this directory as the
canonical in-repo references for the frontend quality refresh. The external
`../ergon_fe_design_system` folder remains a historical archive only; cohort-era
copy in those source materials is not current product language.

- `current-experiment-page.png`: captured from the live dashboard at
  `http://localhost:3001/experiments/52287ee2-8868-4959-951e-053f1a94c992`.
- `archive-experiment-page.png`: copied from the old design archive,
  `ergon_fe_design_system/screenshots/03-eval-slides.png`.
- `current-run-workspace.png`: captured from the live dashboard at
  `http://localhost:3001/run/2709c08b-de67-402c-b081-18ee5994ee33`.
- `archive-run-workspace.png`: copied from the old design archive,
  `ergon_fe_design_system/screenshots/slide-08-lr-v2.png`.
- `current-rubric-drawer.png`: captured from the live dashboard after opening
  the run task workspace evaluation tab.
- `archive-rubric-drawer.png`: captured from slide 13 of the old local design
  deck at `ergon_fe_design_system/index.html`.

Refresh commands used for the live screenshots:

```sh
pnpm -C ergon-dashboard exec playwright screenshot --full-page --viewport-size=2048,1228 \
  http://localhost:3001/experiments/52287ee2-8868-4959-951e-053f1a94c992 \
  docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-experiment-page.png

pnpm -C ergon-dashboard exec playwright screenshot --full-page --viewport-size=2048,1228 \
  http://localhost:3001/run/2709c08b-de67-402c-b081-18ee5994ee33 \
  docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-run-workspace.png
```
