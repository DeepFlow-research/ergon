# P0 — Design System Foundations

**Goal**: Establish the correct token system, fonts, and shared app shell so every subsequent phase builds on the right base.

**Addresses**: 1.1 (topbar), 3.5 (fonts), 3.10 (tokens), 5.4 (segmented controls)

---

## Task 0.1 — Design tokens in globals.css

**File**: `src/app/globals.css`

Replace the minimal `:root` block with the full spec token set:

```css
:root {
  /* Surfaces */
  --paper: #f6f7f9;
  --paper-2: #eef0f3;
  --paper-3: #e6e9ee;
  --card: #ffffff;
  --ink: #0c1118;
  --ink-2: #1f2733;
  --muted: #64707f;
  --faint: #98a2b1;
  --line: #e2e6ec;
  --line-strong: #cdd3dc;

  /* Status — oklch */
  --pending: oklch(0.72 0.02 250);
  --ready: oklch(0.74 0.10 240);
  --running: oklch(0.78 0.14 80);
  --completed: oklch(0.70 0.13 155);
  --failed: oklch(0.68 0.18 22);
  --cancelled: oklch(0.62 0.02 260);

  /* Accent — indigo, selection/pin only */
  --accent: oklch(0.62 0.16 252);
  --accent-soft: oklch(0.94 0.04 252);
  --accent-ink: oklch(0.32 0.12 252);

  /* Radii */
  --radius: 10px;
  --radius-sm: 6px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgb(12 17 24 / 0.04);
  --shadow: 0 1px 2px rgb(12 17 24 / 0.05), 0 4px 12px rgb(12 17 24 / 0.04);
  --shadow-pop: 0 8px 24px rgb(12 17 24 / 0.08), 0 1px 2px rgb(12 17 24 / 0.05);

  /* Fonts */
  --font: "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

Remove the `font-family: Arial, Helvetica, sans-serif` from the body rule. Add `font-family: var(--font);`.

Remove dark-mode `prefers-color-scheme` overrides (the spec is light-only).

**Checklist**:
- [ ] All 22 tokens present
- [ ] Body uses `var(--font)`
- [ ] No dark-mode overrides remain
- [ ] Existing components don't break (hardcoded hex still works, but new work should prefer tokens)

---

## Task 0.2 — Swap fonts: Geist → Inter + JetBrains Mono

**File**: `src/app/layout.tsx`

Current loads Geist via `next/font/local`. Replace with:

```tsx
import { Inter, JetBrains_Mono } from "next/font/google";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});
```

Apply both CSS variable classes to `<body>`. Update `globals.css` to reference them:

```css
:root {
  --font: var(--font-inter), ui-sans-serif, system-ui, sans-serif;
  --mono: var(--font-jetbrains-mono), ui-monospace, SFMono-Regular, monospace;
}
```

**Checklist**:
- [ ] `Inter` and `JetBrains Mono` are loaded from Google Fonts via next/font
- [ ] CSS variables `--font` and `--mono` resolve correctly
- [ ] No Geist references remain
- [ ] Typecheck passes

---

## Task 0.3 — Tailwind config: add features/ content path

**File**: `tailwind.config.ts`

Add `./src/features/**/*.{js,ts,jsx,tsx}` to the `content` array so Tailwind purges correctly for feature components.

Also extend the theme to reference CSS custom properties where helpful:

```ts
theme: {
  extend: {
    colors: {
      paper: "var(--paper)",
      "paper-2": "var(--paper-2)",
      card: "var(--card)",
      ink: "var(--ink)",
      muted: "var(--muted)",
      faint: "var(--faint)",
      line: "var(--line)",
      accent: "var(--accent)",
    },
    borderRadius: {
      card: "var(--radius)",
      sm: "var(--radius-sm)",
    },
    boxShadow: {
      card: "var(--shadow-sm)",
      pop: "var(--shadow-pop)",
    },
    fontFamily: {
      sans: ["var(--font)"],
      mono: ["var(--mono)"],
    },
  },
},
```

---

## Task 0.4 — Create global Topbar component

**New file**: `src/components/shell/Topbar.tsx`

Spec defines:
- 56px height, white bg, 1px bottom border
- Left: Ergon logo (22×22 dark square with cutout) + "Ergon" wordmark + 5 nav links
- Right: Search bar (280px) + context CTA button (optional) + user avatar (28px circle)

Nav links: `Cohorts | Runs | Training | Models | Settings`
- Active link: dark text + `var(--paper-2)` background, 6px radius
- Inactive: muted text

```tsx
interface TopbarProps {
  activeTab?: "cohorts" | "runs" | "training" | "models" | "settings";
  cta?: { label: string; href?: string; onClick?: () => void };
}
```

The search bar is non-functional for now (placeholder) — will wire up in P4.

The user avatar uses initials — can be hardcoded `JM` for now or pulled from a context.

---

## Task 0.5 — Create AppShell layout wrapper

**New file**: `src/components/shell/AppShell.tsx`

Wraps every page: `<Topbar />` + `<main>{children}</main>`. The main area takes the remaining viewport height.

**Edit**: `src/components/common/ClientLayout.tsx` or `src/app/layout.tsx` to include `<AppShell>` around page content.

Page-specific headers (like the run breadcrumb bar) render **below** the topbar, inside the page component. The topbar is always present.

---

## Task 0.6 — StatusBadge / pill alignment

**File**: `src/components/common/StatusBadge.tsx`

Update pill color values to match the spec's oklch values. Add the two variants:

1. **Outline pill** (`.pill`): white bg, 1px border `var(--line)`, 6px color swatch dot, 11px/500 text.
2. **Solid pill** (`.pill--solid`): tinted bg/border/text per status:
   - running: bg `oklch(0.96 0.04 80)`, border `oklch(0.85 0.10 80)`, text `oklch(0.42 0.12 65)`
   - completed: bg `oklch(0.96 0.04 155)`, border `oklch(0.85 0.10 155)`, text `oklch(0.40 0.12 155)`
   - failed: bg `oklch(0.96 0.04 22)`, border `oklch(0.85 0.10 22)`, text `oklch(0.40 0.16 22)`
   - etc.

Add `pulse` animation for running swatch dot.

---

## Task 0.7 — Segmented control component

Either add a reusable `<SegmentedControl>` component or define a Tailwind utility pattern matching:
- `inline-flex border border-line rounded-[7px] bg-paper p-0.5 text-xs`
- Active segment: `bg-card text-ink shadow-card rounded-[5px]`
- Inactive: `text-muted`

This pattern is used in: cohort list filters, cohort detail chart toggle, run header Live/Timeline toggle, graph depth selector, runs list filter.

---

## Verification

After P0:
- [ ] `npm run typecheck` passes
- [ ] All existing e2e tests still pass
- [ ] Every page has the 5-tab topbar
- [ ] Fonts render as Inter + JetBrains Mono (visual check)
- [ ] Token CSS variables are applied to body
