# Ergon Design Spec — Summary of Intent

> Source: `ergon.zip` — a 12-slide HTML/CSS/JS design deck (1920×1080 per slide).

## Core philosophy

**"Light, dense, neutral. One accent. Status colors carry the meaning; chrome stays out of the way so the graph can speak."**

Surface is `Light · paper`. Typography is `Inter` (UI) + `JetBrains Mono` (data / code). The only accent is indigo — used *exclusively* for selection rings and snapshot pins, never decoratively.

---

## The 8 surfaces

The design spec defines 8 distinct UI surfaces, presented as 12 slides (some are transition specs):

### 1. Cohort list (slide 03)

- **Global topbar**: `56px` height, white card background, 1px bottom border.
  - Left: **Ergon logo + wordmark**, then a **5-tab nav**: `Cohorts | Runs | Training | Models | Settings`.
  - Right: **Search bar** (`⌕ Search cohorts, runs, tasks… ⌘K`), a **primary CTA button** (`+ New cohort`), and a **user avatar circle** (`JM`).
- **Page header**: `Workspace · diamond` kicker, `Cohorts` h1, subtitle (`38 active · 2 need attention · last activity 4m ago`).
- **Filter segments** (two rows):
  - Status: `All · 42 | Active · 38 | Running · 6 | Needs attention · 2 | Archived · 4`
  - Sort: `Recent | Score | Failure rate | Runs`
- **Dense data table** inside a `.card`:
  - 7 columns: `Cohort | Runs | Avg score | Failure | Runtime · last activity | Status | ›`
  - Header: 11px uppercase, `#98a2b1` (faint).
  - Rows: cohort name + mono ID, mono data cells, `pill--solid` status badges, right-aligned chevron.
  - 8 sample rows shown (swe-bench, princeton-shrimp, swe-gym, etc.).
- **Footer**: `Showing 8 of 42 cohorts` + live update indicator with green dot.

### 2. Cohort detail (slide 04)

- Same topbar as above.
- **Breadcrumb**: `Cohorts › swe-bench-verified · sonnet-4.5 · v0.7.2`.
- **Header**: Cohort name h1, subtitle (`500 runs · started 2026-04-25 18:12 · created by jm`), action buttons: `Compare | Re-run failed | Open in training`.
- **5 summary metric tiles** (key metrics, each in a `.card`):
  - `Resolution: 62.4%` (▲ 3.1pp vs v0.7.1)
  - `Runs · pass / fail: 312 / 188` (progress bar)
  - `Avg runtime: 2:14` (min · p95 4:32)
  - `Avg tasks: 11.4` (2.1 levels deep · 1.7 retries)
  - `Cost: $84.20` ($0.17 / run · 41M tokens)
- **Two-column split below**:
  - Left: Score distribution chart (scatter/histogram/curve toggle, SVG scatter of pass vs fail vs running).
  - Right: Runs list card with header (`500 total · 6 running`), filter segments (`All | Running | Failed`), and scrollable run rows (id, status pill, time, score).

### 3. Run workspace — live (slide 05)

The main debugger surface. Three-row grid: `auto 1fr 300px`.

**Row 1 — Run header strip** (card background, border-bottom):
- Left: breadcrumb (`Cohorts › swe-bench-verified · sonnet-4.5 › django__django-12345`), run name + status pill + `live · 1m 42s` kicker.
- Right: **inline stats**: `Tasks: 2·2·1·5 | Tokens: 142k | Cost: $0.18 | Score: —`, then `Re-run` button and `⋯` ghost button.

**Row 2 — Graph stage** (dot-grid paper background):
- Floating controls top-left: zoom `＋−⌂`, depth selector `1|2|3|all`, search input.
- **Minimap** top-right (200×130px card with colored rectangles + accent selection rect).
- **Legend** bottom-left (completed/running/ready/pending/failed dots).
- **Graph SVG**: dashed container boxes (`diamond_root`), nodes with status-colored fills and dot indicators. Edges between containers with I/O ports.

**Row 3 — Activity stack dock** (300px, light `#fafbfc` background, NOT dark):
- Header bar: `ACTIVITY STACK` label + `Live · auto-tail` green pill + `seq 0 — 214 · streaming` + right legend dots.
- **Left rubric**: "Concurrent activity / Bars stack only when they overlap."
- **Time axis**: mono timestamps (21:33 → 21:40).
- **Stacked bars**: event bars colored by **kind** (NOT status):
  - graph_mutation = magenta/pink
  - task_execution = violet/purple
  - tool_call = amber
  - message = cyan
  - resource = green
  - eval = red
  - transition = blue
- Each bar has a **start marker** (circle) and **rounded pill shape**.
- **NOW cursor**: green pulsing line + `NOW` pill at leading edge.
- **Footer hints**: "Color = kind | Vertical stack = overlap | Click bar = select task/span | Click ● = lock graph above to that snapshot | Auto-tailing · new events append at right"

### 4. Run workspace — drawer open + snapshot (slide 06)

Same as slide 05 but with:
- **Snapshot pin** on the timeline at seq 42 (indigo vertical line + `SEQ 42` pill).
- Header gets: `graph · seq 42 · 21:36:14` chip.
- **Right drawer** (460px, `shadow-pop`, inside graph stage):
  - Header: `Task workspace` title, pin/close buttons, task name `run_failing_test` + running pill, breadcrumb path.
  - **Tab row**: `Overview | Transitions | Generations | Resources | Evals (2) | Logs`.
  - **Content sections**: Worker info, Transitions (status pill pairs with seq + times), Current turn (tool call card with command + error), Evals on this task (judge running + harness passed cards with scores), Resources at seq 42 (file list).
  - **Footer bar**: `Open in workspace` button + `Jump to live →`.

### 5. Recursive nesting (slide 07)

Same workspace, but graph at depth=2 shows:
- `diamond_root` outer container with L→R flow.
- `planning` (2 nodes), `exploration` (contains `repro_loop` nested sub-DAG with 6 nodes, retry back-edges), `implementation` (4 nodes, fan-out/join), `evaluation` (3 nodes).
- I/O ports (triangles) on container edges.
- Inter-container edges with arrow markers.
- `task ›` input label, `› result` output label.

### 6. Edge states (slide 08)

Three cards: Empty cohort, Run · failed, Connection · stale + Unhandled mutation + No graph.

### 7–9. Transitions (slides 09–11)

Three storyboard transition specs:
- T1: Cohort row → run workspace (320ms, shared element morph).
- T2: Graph node click → drawer (260ms, selection ring + slide).
- T3: Click event → graph snapshot (180ms per node delta).

### 10. Information architecture (slide 12)

Four-column summary: `Cohorts → Cohort detail → Run workspace → Task drawer`. "The dashboard is a funnel."

---

## Design system tokens (from styles.css)

### Surfaces
| Token | Value | Usage |
|-------|-------|-------|
| `--paper` | `#f6f7f9` | Page background |
| `--paper-2` | `#eef0f3` | Secondary surface, kickers |
| `--paper-3` | `#e6e9ee` | Tertiary |
| `--card` | `#ffffff` | Card backgrounds |
| `--ink` | `#0c1118` | Primary text |
| `--ink-2` | `#1f2733` | Secondary text |
| `--muted` | `#64707f` | Muted text |
| `--faint` | `#98a2b1` | Faint text, column headers |
| `--line` | `#e2e6ec` | Borders |
| `--line-strong` | `#cdd3dc` | Stronger borders, dashes |

### Status colors (oklch)
| Status | Value |
|--------|-------|
| pending | `oklch(0.72 0.02 250)` — slate |
| ready | `oklch(0.74 0.10 240)` — sky |
| running | `oklch(0.78 0.14 80)` — amber |
| completed | `oklch(0.70 0.13 155)` — emerald |
| failed | `oklch(0.68 0.18 22)` — rose |
| cancelled | `oklch(0.62 0.02 260)` |

### Accent
| Token | Value |
|-------|-------|
| `--accent` | `oklch(0.62 0.16 252)` — indigo |
| `--accent-soft` | `oklch(0.94 0.04 252)` |
| `--accent-ink` | `oklch(0.32 0.12 252)` |

### Activity stack kind colors (from deck.js)
| Kind | Fill | Text |
|------|------|------|
| graph_mutation | `oklch(0.78 0.14 305)` magenta | white |
| task_execution | `oklch(0.74 0.16 295)` violet | white |
| tool_call | `oklch(0.78 0.16 60)` amber | dark |
| message | `oklch(0.76 0.13 200)` cyan | dark |
| resource | `oklch(0.74 0.13 155)` green | dark |
| eval | `oklch(0.70 0.18 25)` red | white |
| transition | `oklch(0.74 0.10 240)` blue | white |

### Typography
| Role | Size | Tracking |
|------|------|----------|
| Display | 56px | -3% |
| Title | 28px | -2% |
| Body | 14px | 0 |
| UI | 12px | 0 |
| Caption | 11px | +1% |

### Spacing / radii
- `--radius`: 10px (cards)
- `--radius-sm`: 6px (pills, nodes)
- Topbar: 56px height, 24px horizontal padding
- Page content: 32–48px padding
- Cards: `shadow-sm` border

### Fonts
- `Inter` 400/500/600 — sans body
- `JetBrains Mono` 400/500 — monospace data
