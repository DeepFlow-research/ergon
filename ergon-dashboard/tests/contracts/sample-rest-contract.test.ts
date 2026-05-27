import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

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
