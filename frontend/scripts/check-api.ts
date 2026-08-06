/**
 * API contract check for either the Next mock gateway or FastAPI.
 * Run: npm run check:api -- [baseUrl] [--mock]
 */
import {
  ConstituentsSchema,
  DataFreshnessReportSchema,
  ForecastHistorySchema,
  ForecastRecordSchema,
  HistorySchema,
  MarketOverviewSchema,
  ModelStatusReportSchema,
  PerformanceSeriesSchema,
  QuoteSchema,
  RiskDashboardSchema,
  SimulationSchema,
  StrategyMetricsSchema,
  SystemStatusSchema,
} from "../lib/api/types";
import { z } from "zod";

const BASE = process.argv[2] ?? "http://localhost:3000";
const MOCK_MODE = process.argv.includes("--mock") || BASE.includes(":3000");

let failures = 0;

/**
 * Endpoints whose data comes from the `quant` schema, which stays empty until
 * an inference runner writes to it. A 503 there is the designed answer, not a
 * regression — but the payload must still validate once data arrives, so the
 * schema check runs whenever the endpoint does return 200.
 */
async function checkPendingPipeline(path: string, schema: z.ZodTypeAny) {
  try {
    const res = await fetch(`${BASE}${path}`);
    if (res.status === 503) {
      console.log(`○ ${path} → 503 (chưa có model pipeline, đúng thiết kế)`);
      return;
    }
    if (res.status !== 200) {
      failures++;
      console.error(`✗ ${path} — expected 200 or 503, got ${res.status}`);
      return;
    }
    const parsed = schema.safeParse(await res.json());
    if (!parsed.success) {
      failures++;
      console.error(`✗ ${path} — schema mismatch:`);
      console.error(parsed.error.issues.slice(0, 5));
    } else {
      console.log(`✓ ${path}`);
    }
  } catch (e) {
    failures++;
    console.error(`✗ ${path} — ${(e as Error).message}`);
  }
}

async function check(path: string, schema: z.ZodTypeAny, expectStatus = 200) {
  try {
    const res = await fetch(`${BASE}${path}`);
    if (res.status !== expectStatus) {
      failures++;
      console.error(`✗ ${path} — expected ${expectStatus}, got ${res.status}`);
      return;
    }
    if (expectStatus !== 200) {
      console.log(`✓ ${path} → ${res.status}`);
      return;
    }
    const json = await res.json();
    const parsed = schema.safeParse(json);
    if (!parsed.success) {
      failures++;
      console.error(`✗ ${path} — schema mismatch:`);
      console.error(parsed.error.issues.slice(0, 5));
    } else {
      console.log(`✓ ${path}`);
    }
  } catch (e) {
    failures++;
    console.error(`✗ ${path} — ${(e as Error).message}`);
  }
}

const ModelsListSchema = z.object({
  models: z.array(
    z.object({
      slug: z.string(),
      name: z.string(),
      code: z.string(),
      markets: z.array(z.string()),
      category: z.string(),
      status: z.string(),
      version: z.string(),
      horizons: z.array(z.number()),
      access: z.enum(["public", "members"]),
      locked: z.boolean(),
      featured: z.boolean(),
      tagline: z.object({ vi: z.string(), en: z.string() }),
      key_output: z.object({ vi: z.string(), en: z.string() }),
      sparkline: z.array(z.number()).nullable(),
      sparkline_label: z
        .object({ vi: z.string(), en: z.string() })
        .nullable(),
      updated_at: z.string(),
    })
  ),
});

const ModelDetailSchema = ModelsListSchema.shape.models.element.extend({
  show_forecast: z.boolean(),
  show_performance: z.boolean(),
  description: z.record(z.string(), z.unknown()),
  architecture: z.array(z.unknown()).nullable(),
  research_profile: z.record(z.string(), z.unknown()).nullable(),
});

const LatestSchema = z.object({ records: z.array(ForecastRecordSchema) });

const StrategiesListSchema = z.object({
  strategies: z.array(
    z.object({
      slug: z.string(),
      name: z.object({ vi: z.string(), en: z.string() }),
      summary: z.object({ vi: z.string(), en: z.string() }),
      system_slug: z.string(),
      result_type: z.string(),
      asset: z.string(),
      timeframe: z.string(),
      benchmark: z.object({ vi: z.string(), en: z.string() }),
      period_start: z.string(),
      period_end: z.string(),
      fees_note: z.object({ vi: z.string(), en: z.string() }),
      slippage_note: z.object({ vi: z.string(), en: z.string() }),
      split_note: z.object({ vi: z.string(), en: z.string() }),
      seed_note: z.object({ vi: z.string(), en: z.string() }),
      model_version: z.string(),
      code_version: z.string(),
      headline: z.object({
        totalReturn: z.number().nullable(),
        netPoints: z.number().nullable(),
        trades: z.number().nullable(),
      }),
    })
  ),
});

const StrategyDetailSchema = StrategiesListSchema.shape.strategies.element.extend({
  caveats: z.object({ vi: z.array(z.string()), en: z.array(z.string()) }),
  provenance: z.record(z.string(), z.unknown()),
});

async function main() {
  await check("/api/v1/market/overview", MarketOverviewSchema);
  await check("/api/v1/market/VNINDEX/quote", QuoteSchema);
  await check("/api/v1/market/VN30/quote", QuoteSchema);
  await check("/api/v1/market/VN30F1M/quote", QuoteSchema);
  await check("/api/v1/market/VNINDEX/history?count=250", HistorySchema);
  await check("/api/v1/market/vn30/constituents", ConstituentsSchema);
  await checkPendingPipeline("/api/v1/market/risk", RiskDashboardSchema);
  await check("/api/v1/models", ModelsListSchema);
  for (const slug of ["raemf-mc", "rarf-fhe", "dynamic-graph", "msdp"]) {
    await check(`/api/v1/models/${slug}`, ModelDetailSchema);
    if (!MOCK_MODE) await check(`/api/v1/models/${slug}/latest`, z.any(), 404);
  }
  await check(
    "/api/v1/models/vn30-equity-intelligence/latest",
    LatestSchema
  );
  await check(
    "/api/v1/models/vn30-equity-intelligence/history",
    ForecastHistorySchema
  );
  await check("/api/v1/strategies", StrategiesListSchema);
  for (const slug of [
    "vn30f1m-validation-2024",
    "vn30f1m-walk-forward",
    "vn30f1m-multiseed-test",
  ]) {
    await check(`/api/v1/strategies/${slug}`, StrategyDetailSchema);
    await check(`/api/v1/strategies/${slug}/performance`, PerformanceSeriesSchema);
    await check(`/api/v1/strategies/${slug}/metrics`, StrategyMetricsSchema);
  }
  // Only the multi-seed run produced a distribution over seeds
  await check(
    "/api/v1/strategies/vn30f1m-multiseed-test/simulations",
    SimulationSchema
  );
  await check(
    "/api/v1/strategies/vn30f1m-validation-2024/simulations",
    z.any(),
    404
  );
  await check("/api/v1/status", SystemStatusSchema);
  await check("/api/v1/data-freshness", DataFreshnessReportSchema);
  await check("/api/v1/model-status", ModelStatusReportSchema);

  if (MOCK_MODE) {
    // Simulated states (§16.4) exist only in the local mock gateway.
    await check("/api/v1/market/overview?mock_state=stale", MarketOverviewSchema);
    await check("/api/v1/market/overview?mock_state=empty", MarketOverviewSchema);
    await check("/api/v1/market/overview?mock_state=error", z.any(), 500);
    await check("/api/v1/market/overview?mock_state=maintenance", z.any(), 503);
  }
  await check("/api/v1/models/nonexistent/latest", z.any(), 404);

  console.log(
    failures === 0 ? "\nAll API checks passed." : `\n${failures} check(s) FAILED.`
  );
  process.exit(failures === 0 ? 0 : 1);
}

main();
