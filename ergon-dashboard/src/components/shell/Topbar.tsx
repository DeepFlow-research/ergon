"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Experiments", href: "/experiments" },
  { label: "Cohorts", href: "/" },
  { label: "Runs", href: "/runs" },
  { label: "Training", href: "/training" },
  { label: "Models", href: "/models" },
  { label: "Settings", href: "/settings" },
] as const;

function isActive(href: string, pathname: string): boolean {
  if (href === "/") {
    return pathname === "/" || pathname.startsWith("/cohorts");
  }
  if (href === "/experiments") {
    return pathname.startsWith("/experiments");
  }
  if (href === "/runs") {
    return pathname.startsWith("/run/") || pathname.startsWith("/runs");
  }
  return pathname.startsWith(href);
}

export function Topbar() {
  const pathname = usePathname();

  return (
    <header
      className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--line)] bg-[var(--card)] px-6"
      data-testid="topbar"
    >
      <div className="flex items-center gap-8">
        {/* Logo + wordmark */}
        <Link
          href="/"
          className="flex items-center gap-2.5 text-[15px] font-semibold tracking-[-0.01em] text-[var(--ink)]"
        >
          <span className="relative inline-block size-[22px] rounded-[5px] bg-[var(--ink)]">
            <span
              className="absolute inset-[5px] rounded-[2px] bg-[var(--paper)]"
              style={{
                clipPath:
                  "polygon(0 0, 100% 0, 100% 35%, 35% 35%, 35% 65%, 100% 65%, 100% 100%, 0 100%)",
              }}
              aria-hidden
            />
          </span>
          Ergon
        </Link>

        {/* Navigation — hidden on small screens */}
        <nav className="hidden gap-1 md:flex" data-testid="topbar-nav">
          {NAV_ITEMS.map(({ label, href }) => {
            const active = isActive(href, pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] no-underline transition-colors ${
                  active
                    ? "bg-[var(--paper-2)] text-[var(--ink)]"
                    : "text-[var(--muted)] hover:text-[var(--ink)]"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-4">
        {/* Search — hidden on smaller viewports */}
        <div
          className="hidden w-[280px] items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--paper)] px-2.5 py-1.5 text-xs text-[var(--muted)] lg:flex"
          data-testid="topbar-search"
        >
          <span className="opacity-50">⌕</span>
          <span>Search experiments, cohorts, runs, tasks…</span>
          <kbd className="ml-auto rounded border border-[var(--line)] bg-[var(--card)] px-1.5 py-0.5 font-mono text-[10px]">
            ⌘K
          </kbd>
        </div>

        {/* User avatar */}
        <div
          className="grid size-7 place-items-center rounded-full bg-[var(--ink)] text-[11px] font-semibold text-[var(--paper)]"
          data-testid="user-avatar"
        >
          JM
        </div>
      </div>
    </header>
  );
}
