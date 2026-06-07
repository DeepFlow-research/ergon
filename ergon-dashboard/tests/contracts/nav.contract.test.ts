import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

test("top navigation only exposes current product surfaces", () => {
  const source = fs.readFileSync(path.join(process.cwd(), "src/components/shell/Topbar.tsx"), "utf8");

  assert.match(source, /label: "Experiments"/);
  assert.match(source, /label: "Samples"/);
  assert.doesNotMatch(source, /label: "Models"/);
  assert.doesNotMatch(source, /label: "Settings"/);
});

test("font CSS variables include browser-safe fallbacks", () => {
  const source = fs.readFileSync(path.join(process.cwd(), "src/app/globals.css"), "utf8");

  assert.match(source, /--font:\s*var\(--font-inter,\s*Inter\)/);
  assert.match(source, /--mono:\s*var\(--font-jetbrains-mono,\s*"JetBrains Mono"\)/);
});
