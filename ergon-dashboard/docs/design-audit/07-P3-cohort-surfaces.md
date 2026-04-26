# P3 — Cohort Surfaces

**Goal**: Bring the cohort list, cohort detail, and edge states into spec alignment.

**Addresses**: 1.2 (cohort detail), 1.3 (edge states), 2.13 (table row structure), and partial 3.6 (pill styling applied here)

---

## Task 3.1 — Cohort list table alignment

**File**: `src/components/cohorts/CohortListView.tsx` (~669 lines)

### Page header
Current has its own header with title + stats + filters. With P0's Topbar in place, this page should:

1. Remove any duplicate navigation chrome.
2. Keep the page-level header: `Workspace · diamond` kicker, `Cohorts` h1, subtitle.
3. **Add two rows of segmented controls** (both currently partially exist):
   - Status: `All · 42 | Active · 38 | Running · 6 | Needs attention · 2 | Archived · 4`
   - Sort: `Recent | Score | Failure rate | Runs`

### Table columns (7-column grid)
Spec: `grid-template-columns: 2.6fr 1fr 1fr 1fr 1.4fr 1fr 0.8fr`

| Column | Header | Cell content |
|--------|--------|-------------|
| Cohort | `COHORT` | Name (font-weight 600) + mono ID sub-line (`cohort_001`) |
| Runs | `RUNS` | Mono number |
| Avg score | `AVG SCORE` | Mono percentage |
| Failure | `FAILURE` | Mono percentage, color-coded: >30% red, >15% amber, else muted |
| Runtime · last activity | `RUNTIME · LAST ACTIVITY` | Runtime + relative time (muted text) |
| Status | `STATUS` | `pill--solid` badge |
| (chevron) | — | Right-aligned `›` in faint color |

Header row: `padding: 12px 20px; border-bottom: 1px solid var(--line); font-size: 11px; color: var(--faint); text-transform: uppercase; letter-spacing: 0.08em;`

Data rows: `padding: 14px 20px; border-bottom: 1px solid var(--line); font-size: 13px; align-items: center;`

### Footer
`Showing N of M cohorts` + `Updated HH:MM:SS · live ●` (green dot).

---

## Task 3.2 — Cohort detail: metric tiles

**File**: `src/components/cohorts/CohortDetailView.tsx` (~216 lines)

### Breadcrumb
`Cohorts › cohort-name` with muted `Cohorts` link and ink-colored current name.

### Header
- Cohort name h1 (30px, -0.025em tracking)
- Subtitle: `N runs · started DATE · created by USER`
- Action buttons: `Compare | Re-run failed | Open in training` (primary = `Open in training`)

### 5 summary metric tiles
5-column grid, each a `.card` with `padding: 18px 20px`:

1. **Resolution**: `section-title` label, large number (34px, -0.02em), delta sub-line (green for improvement).
2. **Runs · pass / fail**: large `312 / 188` (188 in muted), 6px progress bar below (green/red split).
3. **Avg runtime**: large `2:14`, sub-line `min · p95 4:32`.
4. **Avg tasks**: large `11.4`, sub-line `2.1 levels deep · 1.7 retries`.
5. **Cost**: large `$84.20`, sub-line `$0.17 / run · 41M tokens`.

Data comes from `useCohortDetail().detail.summary` — wire up whatever fields are available from the API. Use `—` for missing fields.

### Two-column content split
Below the tiles: `grid-template-columns: 1.05fr 1fr; gap: 16px`.

**Left card: Score distribution chart**
- Header: `SCORE DISTRIBUTION` section-title + description + `Scatter | Histogram | Curve` segmented control
- Chart area: For MVP, render a simple SVG scatter plot (or use a lightweight chart library). Show completed runs as green dots, failed as red dots, running as amber dots with white stroke. Axes: x = runtime, y = score.
- If no charting library is available, render a placeholder with the correct card frame.

**Right card: Runs list**
- Header: `RUNS` section-title + `N total · M running` + `All | Running | Failed` filter segment
- Scrollable list of run rows: mono run ID, status pill, mono runtime, mono score
- Each row: `grid-template-columns: 1.6fr 0.7fr 0.7fr 1fr; gap: 12px; padding: 13px 20px;`

---

## Task 3.3 — Edge states

### Empty cohort
When a cohort has 0 runs, show in the runs area:
- Dashed border container, paper background, centered content
- 48×48 icon (⊘ in paper-2 bg), h3 "No runs yet", description text, primary "Launch cohort" button

### Failed run
When a run status is `failed`, show at the top of the run workspace:
- Rose-tinted card (`oklch(0.98 0.02 22)` bg, `oklch(0.85 0.10 22)` border)
- Failed pill + seq/time info
- Error task name, mono error message (pre-wrap)
- "Last good state" section with info
- `Re-run from seq 0` primary button + `Replay` secondary

### Connection stale
In `ConnectionStatus.tsx` or as a banner:
- Cancelled dot + "Live socket disconnected" message
- "Falling back to REST · refresh every 5s" sub-text
- If there are unhandled mutations: warning card with amber border

### No graph yet
In `DAGCanvas` when there are no nodes:
- Dashed border container, centered: "Run hasn't emitted nodes yet"

---

## Task 3.4 — Runs page (tab in topbar)

The spec has a `Runs` tab in the topbar. This is currently the `/run/[runId]` legacy route, but there's no "all runs" index page.

For now, the `/` route maps to cohort list. The `Runs` tab can either:
- Link to `/` with a different view mode (table of all runs across cohorts)
- Be marked as "coming soon" in the nav
- Show a filtered version of the cohort list

Recommendation: Skip for now, mark as future work. The tab should exist in the topbar but can link to `/` with a `?view=runs` param or similar.

---

## Verification

After P3:
- [ ] Cohort list table has 7 columns with correct headers and cell formats
- [ ] Failure % is color-coded
- [ ] Cohort detail shows 5 metric tiles
- [ ] Score chart area exists (even if placeholder)
- [ ] Runs list in cohort detail has filter segments
- [ ] Empty cohort state renders correctly
- [ ] Failed run state renders correctly
- [ ] No-graph state renders correctly
- [ ] `cohort.snapshot.spec.ts` still passes
- [ ] New screenshots for cohort list and detail
