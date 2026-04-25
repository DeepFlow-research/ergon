import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const schemasRoot = path.join(projectRoot, "src/generated/events/schemas");
const outputRoot = path.join(projectRoot, "src/generated/events");
const manifestPath = path.join(schemasRoot, "manifest.json");

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

rmSync(path.join(outputRoot, "index.ts"), { force: true });
mkdirSync(outputRoot, { recursive: true });

/**
 * Post-process a json-schema-to-zod@2.7.0 output file for Zod 4 compatibility.
 *
 * The CLI emits Zod 3 syntax (``z.record(valueType)``) that is a type error
 * under Zod 4, which requires ``z.record(keyType, valueType)``.  Rewrite each
 * single-arg ``z.record(...)`` call to the two-arg form with ``z.string()``
 * as the key type — JSON object keys are always strings.
 */
function patchZod4Compat(source) {
  // Match ``z.record(<balanced>)`` with a single argument — the content must
  // not contain a bare top-level comma.  Handles nested parens up to depth 8
  // which is more than enough for our schemas.
  return source.replace(/z\.record\(((?:[^()]|\([^()]*\))*?)\)/g, (full, inner) => {
    // If inner already contains a top-level comma (depth 0), it's a 2-arg call.
    let depth = 0;
    for (let i = 0; i < inner.length; i++) {
      const c = inner[i];
      if (c === "(") depth++;
      else if (c === ")") depth--;
      else if (c === "," && depth === 0) return full;
    }
    return `z.record(z.string(), ${inner})`;
  });
}

for (const entry of manifest) {
  const schemaPath = path.join(schemasRoot, entry.schemaFile);
  const outputPath = path.join(outputRoot, `${entry.modelName}.ts`);
  execFileSync(
    "pnpm",
    [
      "exec",
      "json-schema-to-zod",
      "-i",
      schemaPath,
      "-o",
      outputPath,
      "-n",
      `${entry.modelName}Schema`,
      "-d",
      "10",
    ],
    {
      cwd: projectRoot,
      stdio: "inherit",
    },
  );
  const patched = patchZod4Compat(readFileSync(outputPath, "utf8"));
  writeFileSync(outputPath, patched);
}

const importLines = ['import { z } from "zod";'];
const exportLines = [];
const schemaEntries = [];

for (const entry of manifest) {
  const schemaConst = `${entry.modelName}Schema`;
  importLines.push(`import { ${schemaConst} } from "./${entry.modelName}";`);
  exportLines.push(`export { ${schemaConst} };`);
  exportLines.push(`export type ${entry.modelName} = z.infer<typeof ${schemaConst}>;`);
  schemaEntries.push(`  "${entry.eventName}": ${schemaConst},`);
}

const indexSource = `${importLines.join("\n")}

${exportLines.join("\n")}

export const dashboardEventSchemas = {
${schemaEntries.join("\n")}
} as const;

export type DashboardEventName = keyof typeof dashboardEventSchemas;
`;

writeFileSync(path.join(outputRoot, "index.ts"), `${indexSource}\n`);
