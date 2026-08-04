import { writeFile } from "node:fs/promises";
import path from "node:path";
import { MODELS } from "../config/models";
import { MODEL_RESEARCH } from "../config/model-research";
import { STRATEGIES } from "../config/strategies";

/**
 * Export the frontend's reviewed catalogue fixture into a deterministic JSON
 * snapshot consumed by the FastAPI seeder. Runtime production pages read the
 * seeded database; this script is the explicit publishing boundary.
 */
async function main() {
  const models = MODELS.map((model) => ({
    ...model,
    researchProfile: MODEL_RESEARCH[model.slug] ?? null,
  }));
  const output = {
    schemaVersion: 1,
    models,
    strategies: STRATEGIES,
  };
  const target = path.resolve(process.cwd(), "config", "catalogue.json");
  await writeFile(target, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  console.log(
    `exported ${models.length} models and ${STRATEGIES.length} strategies to ${target}`
  );
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
