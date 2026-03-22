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
