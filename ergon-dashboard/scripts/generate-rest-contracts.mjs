import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const contractsPath = path.resolve(__dirname, "../src/generated/rest/contracts.ts");

const source = readFileSync(contractsPath, "utf8")
  .replace('import { makeApi, Zodios, type ZodiosOptions } from "@zodios/core";\n', "")
  // openapi-zod-client generates z.record(V) but Zod requires z.record(K, V).
  .replace(/z\.record\((?!z\.string\(\))/g, "z.record(z.string(), ");
const endpointMarker = "\nconst endpoints = makeApi([";
const markerIndex = source.indexOf(endpointMarker);

if (markerIndex === -1) {
  throw new Error("Could not find endpoint section in generated REST contracts.");
}

const schemasOnlySource = source.slice(0, markerIndex).trimEnd();

writeFileSync(contractsPath, `${schemasOnlySource}\n`);
