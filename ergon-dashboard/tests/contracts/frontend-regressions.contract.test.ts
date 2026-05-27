import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("experiment detail does not pass server functions into client components", () => {
  const source = readFileSync("src/app/experiments/[experimentId]/page.tsx", "utf8");

  assert.doesNotMatch(source, /getRunHref=\{[a-zA-Z_$][\w$]*\}/);
});

test("run display state keeps live mode separate from graph sequence zero", () => {
  const source = readFileSync("src/components/sample/useSampleDisplayState.ts", "utf8");

  assert.doesNotMatch(source, /snapshotSequence\s*\?\?\s*0/);
});

test("experiment detail sample table exposes each row as sample navigation", () => {
  const source = readFileSync("src/components/experiments/SampleTable.tsx", "utf8");

  assert.match(source, /data-testid=\{`experiment-sample-row-\$\{sample\.sampleId\}`\}/);
  assert.match(source, /href=\{`\/samples\/\$\{sample\.sampleId\}`\}/);
});

test("run workspace can collapse the bottom activity timeline", () => {
  const source = readFileSync("src/components/sample/SampleWorkspacePage.tsx", "utf8");

  assert.match(source, /const \[isTimelineOpen, setIsTimelineOpen\] = useState\(true\)/);
  assert.match(source, /data-testid="activity-timeline-toggle"/);
  assert.match(source, /isTimelineOpen && activities\.length > 0/);
});

test("run workspace keeps replay arrows available outside the timeline panel", () => {
  const source = readFileSync("src/components/sample/SampleWorkspacePage.tsx", "utf8");

  assert.match(source, /data-testid="replay-step-previous"/);
  assert.match(source, /data-testid="replay-step-next"/);
  assert.match(source, /resolveReplayStep\(mutations, snapshotSequence, "previous"\)/);
  assert.match(source, /resolveReplayStep\(mutations, snapshotSequence, "next"\)/);
});

test("run workspace does not render the task inspection placeholder", () => {
  const source = readFileSync("src/components/sample/SampleWorkspacePage.tsx", "utf8");

  assert.doesNotMatch(source, /Task inspection/);
  assert.doesNotMatch(source, /Click node/);
  assert.doesNotMatch(source, /data-testid="workspace-launcher"/);
});

test("sample workspace links back to the owning experiment detail", () => {
  const source = readFileSync("src/components/sample/SampleWorkspacePage.tsx", "utf8");

  assert.match(source, /const experimentHref = runState\?\.experimentId \? `\/experiments\/\$\{runState\.experimentId\}` : "\/experiments"/);
  assert.match(source, /href=\{experimentHref\}/);
});
