# P2 — Activity Stack Alignment

**Goal**: Bring the activity stack (timeline dock) into spec alignment — surface treatment, kind colors, cursor/pin markers, hint row.

**Addresses**: 2.10 (footer hints), 2.11 (snapshot pin + NOW cursor), 3.1 (light vs dark), 3.2 (kind colors), 5.1 (left rubric), 5.2 (time axis)

---

## Decision: Light vs Dark

The spec HTML source uses `background: #fafbfc` (very light) for the activity stack dock. However, the rendered reference screenshots (`slide-07-final.png`) appear to show a **dark** dock.

Looking closely at the final rendered screenshot, the dock IS dark — the deck.js generates a light-background container in the HTML but the rendered screenshots were taken with the dark styling. The current implementation already uses dark (`#070b12`).

**Recommendation**: Keep the **dark dock** — it provides better contrast for the saturated activity bars, and the rendered screenshots (which represent the designer's final intent) show dark. But adjust the header/rubric text styling to match the screenshot: lighter gray text on dark, not the spec HTML's dark-on-light treatment.

If the user prefers light, the changes are: swap `bg-[#070b12]` → `bg-[#fafbfc]`, border color → `var(--line)`, text → `var(--ink)`.

---

## Task 2.1 — Kind color alignment

**File**: `src/features/activity/components/ActivityBar.tsx`

Audit `KIND_STYLES` map against the spec's 7 kind colors:

```
graph_mutation:  fill oklch(0.78 0.14 305)  text white     // magenta
task_execution:  fill oklch(0.74 0.16 295)  text white     // violet
tool_call:       fill oklch(0.78 0.16 60)   text #1a1207   // amber
message:         fill oklch(0.76 0.13 200)  text #06181c   // cyan
resource:        fill oklch(0.74 0.13 155)  text #06180e   // green
eval:            fill oklch(0.70 0.18 25)   text white     // red
transition:      fill oklch(0.74 0.10 240)  text white     // blue
```

Also check the `ActivityKind` type in `src/features/activity/types.ts` — ensure all 7 kinds are defined and mapped.

Each bar should also have a **start marker circle**: 4.5px radius at the left edge, same fill as bar, with a 2px dark stroke (`#0c1118` or `#fafbfc` depending on light/dark dock).

---

## Task 2.2 — NOW cursor (live leading edge)

**File**: `src/features/activity/components/ActivityStackTimeline.tsx`

When in live mode, render at the rightmost event position + 30px:

1. **Vertical line**: 2px wide, `oklch(0.66 0.18 145)` (green), full height of the stack area, pulsing animation.
2. **NOW pill**: positioned above the line, green background, white mono text `NOW` with a pulsing white dot.
3. **Soft fade gradient**: 60px wide linear-gradient from transparent to `oklch(0.96 0.05 145 / 0.35)` at the leading edge, suggesting live append.

---

## Task 2.3 — Snapshot pin (locked sequence)

When the graph is locked to a sequence (via clicking an event marker or timeline scrub):

1. **Indigo vertical line**: 2px, `var(--accent)`, full stack height.
2. **SEQ N pill**: above the line, accent background, white mono text with sequence number.
3. The NOW cursor continues to show at the live edge (both are visible simultaneously).

In the header bar, add: `graph locked · seq N` in accent color when a snapshot is active.

---

## Task 2.4 — Header bar refinement

Current header has: label, live pill, seq range.

Spec header has two sides:
- **Left**: `ACTIVITY STACK` label + `rows are overlap layers, not fixed lanes · streams in real time` description + `Live · auto-tail` green pill + `seq 0 — 214 · streaming` + optional `graph locked · seq N` (accent).
- **Right**: Kind legend — colored dots with labels for all 7 event kinds.

Move the event-type filter pills currently at the bottom to the right side of the header as a **legend** (non-interactive dots + labels), not clickable filters.

If filtering by kind is important to keep, add it as a subtle interaction (clicking a legend dot toggles that kind) but the default should be "all visible, legend is informational".

---

## Task 2.5 — Footer hint row

Replace the current bottom filter pills with:

```
Color = kind · Vertical stack = overlap · Click bar = select task/span ·
Click ● = lock graph above to that snapshot · Auto-tailing · new events append at right
```

Style: `font-size: 10px; color: #a8b0bd;` (faint), flex row with `·` separators.

---

## Task 2.6 — Left rubric

Current left rubric: "Concurrent activity / Bars stack only / when they overlap"

Spec: 140px-wide column with:
```
Concurrent activity (font-weight 600, ink color)
Bars stack only when they overlap. (normal weight, muted)
```

Ensure the column is exactly 140px, with a 16px gap to the bar area. Typography should use the spec's 11px size with 1.45 line-height.

---

## Task 2.7 — Time axis

Spec: mono 10px timestamps in an 8-column grid (e.g., `21:33 | 21:34 | ... | 21:39 · now | 21:40`).

Current implementation likely already has a time axis. Verify:
- Uses `var(--mono)` font
- 10px size
- 8 evenly spaced columns
- Current time slot gets `· now` suffix in green
- Future slots are dimmed (`#cdd3dc`)

---

## Task 2.8 — Playback controls alignment

The spec shows: `⏮⏮ | ▶ | ⏭⏭` buttons + `0.5x | 1x | 2x | 4x` speed selector + `SEQ 0 — 42 OF 214` display.

Current has: Play button + speed dropdown + sequence display. Ensure the layout matches (centered in the header bar, between left info and right legend).

---

## Verification

After P2:
- [ ] Activity bars use the 7 spec kind colors
- [ ] Start marker circles visible on each bar
- [ ] NOW cursor with green pulse at live edge
- [ ] Snapshot pin at locked sequence (indigo)
- [ ] Header has left info + right legend layout
- [ ] Footer has hint text row
- [ ] Left rubric is 140px, properly styled
- [ ] Time axis is 8-column mono with `· now` marker
- [ ] `activity-stack.spec.ts` still passes (update selectors if needed)
- [ ] New screenshot: `activity-stack-aligned.png`
