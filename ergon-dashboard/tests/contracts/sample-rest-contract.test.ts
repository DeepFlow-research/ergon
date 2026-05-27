import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import { schemas } from "../../src/generated/rest/contracts";

const sampleId = "00000000-0000-4000-8000-000000000001";
const taskId = "00000000-0000-4000-8000-000000000002";
const edgeId = "00000000-0000-4000-8000-000000000003";

test("sample detail no longer exposes generic mutation proxy route", () => {
  assert.equal(existsSync("src/app/api/samples/[sampleId]/mutations/route.ts"), false);
});

test("sample workspace loads typed runtime events instead of mutation DTOs", () => {
  const source = readFileSync("src/components/sample/SampleWorkspacePage.tsx", "utf8");

  assert.match(source, /fetch\(`\/api\/samples\/\$\{sampleId\}\/events`\)/);
  assert.match(source, /parseSampleRuntimeEvents/);
  assert.doesNotMatch(source, /\/api\/samples\/\$\{sampleId\}\/mutations/);
});

test("generated REST contract does not expose sample mutations", () => {
  const openapi = readFileSync("src/generated/rest/openapi.json", "utf8");
  const contracts = readFileSync("src/generated/rest/contracts.ts", "utf8");

  assert.doesNotMatch(openapi, /\/samples\/\{sample_id\}\/mutations/);
  assert.doesNotMatch(openapi, /GraphMutationRecordDto/);
  assert.doesNotMatch(contracts, /GraphMutationRecordDto/);
});

test("generated REST contract exposes sample runtime events as a discriminated union", () => {
  const contracts = readFileSync("src/generated/rest/contracts.ts", "utf8");

  assert.match(contracts, /const SampleRuntimeEventView = z\.discriminatedUnion\("eventType"/);
  assert.match(contracts, /eventType: z\.literal\("task\.added"\)/);
  assert.match(contracts, /eventType: z\.literal\("edge\.added"\)/);

  const parsed = schemas.SampleRuntimeEventView.parse({
    eventId: edgeId,
    sampleId,
    timestamp: "2026-05-27T12:00:00Z",
    eventType: "edge.added",
    targetType: "edge",
    targetId: edgeId,
    sourceTaskId: taskId,
    targetTaskId: "00000000-0000-4000-8000-000000000004",
    status: "pending",
    payload: {},
  });

  assert.equal(parsed.eventType, "edge.added");
  assert.throws(() =>
    schemas.SampleRuntimeEventView.parse({
      eventId: edgeId,
      sampleId,
      timestamp: "2026-05-27T12:00:00Z",
      eventType: "not.real",
      targetType: "edge",
      targetId: edgeId,
      payload: {},
    }),
  );
});
