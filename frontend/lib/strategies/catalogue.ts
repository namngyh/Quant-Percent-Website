import "server-only";

import {
  STRATEGIES,
  type StrategyConfig,
} from "@/config/strategies";
import { getHeadline } from "@/lib/performance/reports";

type Headline = ReturnType<typeof getHeadline>;

export interface PublishedStrategyCard
  extends Omit<StrategyConfig, "dataset" | "caveats"> {
  headline: Headline;
}

export interface PublishedStrategyDetail extends PublishedStrategyCard {
  caveats: StrategyConfig["caveats"];
  provenance: { source_project?: string; [key: string]: unknown } | null;
}

interface ApiStrategySummary {
  slug: string;
  name: StrategyConfig["name"];
  summary: StrategyConfig["summary"];
  system_slug: string;
  result_type: StrategyConfig["resultType"];
  asset: string;
  timeframe: string;
  benchmark: StrategyConfig["benchmark"];
  period_start: string;
  period_end: string;
  fees_note: StrategyConfig["feesNote"];
  slippage_note: StrategyConfig["slippageNote"];
  split_note: StrategyConfig["splitNote"];
  seed_note: StrategyConfig["seedNote"];
  model_version: string;
  code_version: string;
  headline: Headline;
}

function usesDatabaseApi() {
  return process.env.DATA_MODE === "api";
}

function apiBase() {
  const base = process.env.API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new Error("API_BASE_URL is required when DATA_MODE=api");
  return base;
}

function toCard(item: ApiStrategySummary): PublishedStrategyCard {
  return {
    slug: item.slug,
    name: item.name,
    summary: item.summary,
    systemSlug: item.system_slug,
    resultType: item.result_type,
    asset: item.asset,
    timeframe: item.timeframe,
    benchmark: item.benchmark,
    periodStart: item.period_start,
    periodEnd: item.period_end,
    feesNote: item.fees_note,
    slippageNote: item.slippage_note,
    splitNote: item.split_note,
    seedNote: item.seed_note,
    modelVersion: item.model_version,
    codeVersion: item.code_version,
    headline: item.headline,
  };
}

function mockCard(strategy: StrategyConfig): PublishedStrategyCard {
  return { ...strategy, headline: getHeadline(strategy) };
}

export async function getPublishedStrategies(): Promise<PublishedStrategyCard[]> {
  if (!usesDatabaseApi()) return STRATEGIES.map(mockCard);
  const response = await fetch(`${apiBase()}/api/v1/strategies`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Backend API ${response.status} for strategies`);
  }
  const payload = (await response.json()) as {
    strategies: ApiStrategySummary[];
  };
  return payload.strategies.map(toCard);
}
