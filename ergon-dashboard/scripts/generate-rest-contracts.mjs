import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const contractsPath = path.resolve(__dirname, "../src/generated/rest/contracts.ts");

let source = readFileSync(contractsPath, "utf8")
  .replace('import { makeApi, Zodios, type ZodiosOptions } from "@zodios/core";\n', "")
  // openapi-zod-client generates z.record(V) but Zod requires z.record(K, V).
  .replace(/z\.record\((?!z\.string\(\))/g, "z.record(z.string(), ")
  // Preserve literal discriminators for generated context-event payload unions.
  .replace(
    /event_type: z\.string\(\)\.optional\(\)\.default\("([^"]+)"\)/g,
    'event_type: z.literal("$1").default("$1")',
  )
  // Preserve literal discriminators for generated context-part unions.
  .replace(
    /part_kind: z\.string\(\)\.optional\(\)\.default\("([^"]+)"\)/g,
    'part_kind: z.literal("$1").default("$1")',
  )
  // Recursive JSON schemas must be lazy or the generated module dereferences
  // JsonValue_Input before it has been initialized.
  .replace(
    /const JsonValue_(Input|Output): z\.ZodType<JsonValue_\1> = z\.union\(\[\n([\s\S]*?)\n\]\);/g,
    "const JsonValue_$1: z.ZodType<JsonValue_$1> = z.lazy(() => z.union([\n$2\n]));",
  );

const sampleRuntimeEventDiscriminators = {
  SampleStatusChangedEventView: "sample.status_changed",
  SampleTaskAddedEventView: "task.added",
  SampleTaskRemovedEventView: "task.removed",
  SampleTaskStatusChangedEventView: "task.status_changed",
  SampleEdgeAddedEventView: "edge.added",
  SampleEdgeRemovedEventView: "edge.removed",
  SampleEdgeStatusChangedEventView: "edge.status_changed",
  SampleWorkerAddedEventView: "worker.added",
  SampleWorkerRemovedEventView: "worker.removed",
  SampleEvaluatorAddedEventView: "evaluator.added",
  SampleEvaluatorRemovedEventView: "evaluator.removed",
  SampleSandboxAddedEventView: "sandbox.added",
  SampleSandboxRemovedEventView: "sandbox.removed",
  SampleAnnotationSetEventView: "annotation.set",
  SampleAnnotationUpdatedEventView: "annotation.updated",
  SampleAnnotationDeletedEventView: "annotation.deleted",
};

for (const [schemaName, eventType] of Object.entries(sampleRuntimeEventDiscriminators)) {
  const pattern = new RegExp(`(const ${schemaName} = z[\\s\\S]*?eventType: )z\\.string\\(\\)(,)`);
  source = source.replace(pattern, `$1z.literal("${eventType}")$2`);
}

const sampleRuntimeEventUnion = `const SampleRuntimeEventView = z.discriminatedUnion("eventType", [
  SampleStatusChangedEventView,
  SampleTaskAddedEventView,
  SampleTaskRemovedEventView,
  SampleTaskStatusChangedEventView,
  SampleEdgeAddedEventView,
  SampleEdgeRemovedEventView,
  SampleEdgeStatusChangedEventView,
  SampleWorkerAddedEventView,
  SampleWorkerRemovedEventView,
  SampleEvaluatorAddedEventView,
  SampleEvaluatorRemovedEventView,
  SampleSandboxAddedEventView,
  SampleSandboxRemovedEventView,
  SampleAnnotationSetEventView,
  SampleAnnotationUpdatedEventView,
  SampleAnnotationDeletedEventView,
]);
`;

source = source.replace("\nconst SampleEventsView =", `\n${sampleRuntimeEventUnion}const SampleEventsView =`);
source = source.replace("  SampleEventsView,", "  SampleRuntimeEventView,\n  SampleEventsView,");

const endpointMarker = "\nconst endpoints = makeApi([";
const markerIndex = source.indexOf(endpointMarker);

if (markerIndex === -1) {
  throw new Error("Could not find endpoint section in generated REST contracts.");
}

const schemasOnlySource = source.slice(0, markerIndex).trimEnd();

writeFileSync(
  contractsPath,
  `/* eslint-disable @typescript-eslint/no-empty-object-type */\n${schemasOnlySource}\n`,
);
