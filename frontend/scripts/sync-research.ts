/**
 * Copy the network model's published artifacts into the website.
 *
 * DynamicGraph's `export-website` command writes to its own
 * `artifacts/latest/` directory and stops there; getting those files in front
 * of a visitor was a manual copy nobody had written down. The ranking table,
 * the cluster charts and the relationship map all read these two files, so
 * without this step they silently keep showing the previous run.
 *
 *   npm run research:sync
 *   npm run research:sync -- --from <dir>
 *
 * Run it after the model finishes:
 *   python -m dynamicgraph.cli export-website --config config/local.yaml
 *
 * `--from` points at another artifacts/latest directory. A descriptive-only
 * refresh — the fast path that recomputes the network without retraining the
 * stress classifier — writes outside the repository so it cannot overwrite
 * the committed publication-grade artifacts, and this is how its output gets
 * to the site.
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const fromFlag = process.argv.indexOf("--from");
const SOURCE =
  fromFlag !== -1 && process.argv[fromFlag + 1]
    ? path.resolve(process.argv[fromFlag + 1])
    : path.join(ROOT, "models", "dynamic-graph", "artifacts", "latest");
const TARGET = path.resolve(process.cwd(), "public", "research");

const FILES = [
  { from: "nodes.json", to: "dynamic-graph-nodes.json" },
  { from: "edges.json", to: "dynamic-graph-edges.json" },
];

function main() {
  console.log(`source: ${SOURCE}`);
  if (!existsSync(SOURCE)) {
    console.error(`Model artifacts not found: ${SOURCE}`);
    console.error("Run the model's export-website command first.");
    process.exitCode = 1;
    return;
  }
  mkdirSync(TARGET, { recursive: true });

  for (const file of FILES) {
    const from = path.join(SOURCE, file.from);
    if (!existsSync(from)) {
      console.error(`Missing ${from}`);
      process.exitCode = 1;
      return;
    }
    copyFileSync(from, path.join(TARGET, file.to));
    const rows = JSON.parse(readFileSync(from, "utf8")) as unknown[];
    console.log(`${file.to}: ${rows.length} row(s)`);
  }

  // The run date lives in the manifest, not in the two data files; print it so
  // a stale copy is obvious at the point of copying rather than on the page.
  const manifest = path.join(SOURCE, "latest_dynamicgraph.json");
  if (existsSync(manifest)) {
    const meta = JSON.parse(readFileSync(manifest, "utf8")) as {
      model?: { as_of_date?: string; generated_at?: string };
    };
    console.log(`as_of: ${meta.model?.as_of_date ?? "unknown"}`);
    console.log(`generated: ${meta.model?.generated_at ?? "unknown"}`);
  }
}

main();
