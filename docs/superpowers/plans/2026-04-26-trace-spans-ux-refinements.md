# Trace Spans UX Refinements

Date: 2026-04-26

## Context

The immutable Trace Spans direction is right: the bottom trace should act as a fixed map of the completed run, while clicking or arrowing between events moves the cursor, replays the graph above, and updates the workspace detail. The next set of issues is about legibility: dense events overlap, hover metadata is hard to read, tooltips crop, and some events appear to be hidden or inaccessible.

## 1. JSON Metadata Is Hard To Read

### Problem

The hover metadata is too raw. It technically exposes useful details, but the user has to parse JSON to answer the basic question: "what is this event?"

### Proposed Fix

Use a two-level hover card:

- Summary header: event kind, label, task, sequence, and timestamp.
- Important fields table: fields such as `mutationType`, `targetId`, `actor`, `reason`, `status`, `toolName`, `exitCode`, or `score`.
- Raw JSON collapsed by default under a `Raw payload` disclosure.

The raw JSON should remain available for debugging, but it should not be the first thing the user has to read.

### Acceptance Criteria

- Hovering an event answers "what is this?" without reading raw JSON.
- Raw JSON is still available on demand.
- The same summary fields are reused in the pinned workspace activity detail.

## 2. Hover Cards Crop Off The Top

### Problem

Hover cards can be clipped when the event is near the top of the Trace Spans component. This likely happens because the tooltip is rendered inside an overflow-constrained timeline container.

### Proposed Fix

Make the tooltip viewport-aware:

- Render the hover card as `position: fixed`, or via a small portal attached to `document.body`.
- Compute the hovered marker/bar bounding box.
- Prefer placing the card above the event when there is room.
- Flip below the event when there is not enough space above.
- Clamp left and right positions to the viewport.
- Give the card a `max-height` with internal scroll for larger payloads.

### Acceptance Criteria

- Hovering any visible event never clips the tooltip outside the viewport.
- The hover card remains readable for top-row, bottom-row, far-left, and far-right events.
- Keyboard focus should show the same preview behavior as mouse hover.

## 3. Too Much Overlap

### Problem

Point events and duration spans currently compete for the same visual space. Dense regions become hard to read because markers pile up on top of bars or on top of each other.

### Proposed Fix

Separate the visual grammar:

- Span rows show only duration bars: task executions and sandbox lifetimes.
- Point events render on marker rails, not directly as miniature bars inside the same span rows.
- Dense point events are clustered when they fall within a few pixels of each other.
- A cluster renders as a numbered bubble such as `+4`.
- Hovering or clicking a cluster opens a small list of the events inside that time window.
- Add optional kind filters so the user can hide/show `graph`, `context`, `message`, `artifact`, `evaluation`, and `sandbox` markers.

### Acceptance Criteria

- Overlapping work remains visible as stable bars.
- Dense point events remain inspectable without becoming a pile of dots.
- Markers do not change span row assignment.
- Clusters expose every hidden event through hover or click.

## 4. Missing Dots / Possible Bottom Cropping

### Problem

When moving between examples, the UI reports multiple steps/events, but the corresponding dots are not always visible on the end swim lanes. This may mean markers are rendered below the visible component, hidden by overflow, or compressed into inaccessible rows.

### Proposed Fix

Audit and stabilize the timeline height and scroll behavior:

- Ensure the timeline content height derives from the full layout, including marker rails and bottom padding.
- Add an assertion that every rendered `layout.item` is inside the scrollable timeline bounds.
- Make vertical overflow explicit: if the trace has more rows than fit, the panel should visibly scroll or offer an expand control.
- Add a trace status line, for example: `17 trace rows · 84 events · 0 hidden`.
- If filters are added, report hidden counts explicitly, for example: `12 hidden by filters`.
- Consider an "Expand trace" control for dense runs so users can inspect the full trace without fighting a 300px dock.

### Acceptance Criteria

- If the UI reports events at a point, the user can scroll or expand to see them.
- No event markers silently render outside the component.
- The component distinguishes between events that are hidden by filters, collapsed into clusters, or simply below the current scroll position.

## Implementation Notes

This should follow the immutable Trace Spans acceptance criterion:

- Clicking or arrowing between point events must not change Trace Span bar lengths.
- Clicking or arrowing between point events must not change row assignments.
- Clicking or arrowing should only move the cursor/pin, update selected marker state, replay the top graph, and update the workspace detail.

Suggested implementation order:

1. Stabilize immutable trace derivation and layout.
2. Add marker rails and clustering.
3. Add the improved legend and trace status line.
4. Add viewport-aware hover cards.
5. Reuse the same event summary/debug payload in the workspace detail.
6. Add e2e coverage for no clipping, no relayout on marker click, and cluster inspection.
