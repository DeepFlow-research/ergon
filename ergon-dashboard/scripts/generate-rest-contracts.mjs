import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const contractsPath = path.resolve(__dirname, "../src/generated/rest/contracts.ts");

const source = readFileSync(contractsPath, "utf8")
  .replace('import { makeApi, Zodios, type ZodiosOptions } from "@zodios/core";\n', "")
  // openapi-zod-client generates z.record(V) but Zod requires z.record(K, V).
  .replace(/z\.record\((?!z\.string\(\))/g, "z.record(z.string(), ")
  // Recursive JSON schemas must be lazy or the generated module dereferences
  // JsonValue_Input before it has been initialized.
  .replace(
    /const JsonValue_(Input|Output): z\.ZodType<JsonValue_\1> = z\.union\(\[\n([\s\S]*?)\n\]\);/g,
    "const JsonValue_$1: z.ZodType<JsonValue_$1> = z.lazy(() => z.union([\n$2\n]));",
  );
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
