import { getModel, type ModelConfig } from "@/config/models";
import type {
  ForecastHistory,
  ForecastHistoryPoint,
  ForecastRecord,
} from "@/lib/api/types";
import {
  daySeed,
  gaussian,
  hashSeed,
  mulberry32,
} from "@/lib/mock/seeded-random";
import {
  freshness,
  genHistory,
  marketState,
  type MockState,
} from "@/lib/mock/market";

/** Illustrative forecast records that are deterministic per day. */

export function latestForecasts(
  model: ModelConfig,
  symbol: string,
  state: MockState = "ok"
): ForecastRecord[] {
  if (state === "empty") return [];
  const bars = genHistory(symbol);
  const price = bars[bars.length - 1].close;
  const s = marketState();
  return model.horizons.map((horizon) => {
    const rng = mulberry32(hashSeed("fc", model.slug, symbol, horizon, daySeed()));
    const drift = (s.probability_up - 0.5) * 0.02 * Math.sqrt(horizon);
    const ret = drift + (rng() - 0.5) * 0.004 * horizon;
    const width = s.volatility * Math.sqrt(horizon / 252) * 1.96;
    const value = price * (1 + ret);
    const probUp = Math.min(
      0.85,
      Math.max(0.15, s.probability_up + (rng() - 0.5) * 0.08)
    );
    return {
      ...freshness(state),
      model_id: model.slug,
      model_name: model.name,
      model_version: model.version,
      symbol,
      timeframe: "1D",
      horizon,
      horizon_unit: "trading_days" as const,
      forecast_value: round2(value),
      forecast_return: round4(ret),
      probability_up: round3(probUp),
      probability_down: round3(1 - probUp),
      regime: s.regime,
      regime_probability: s.regime_probability,
      volatility: s.volatility,
      interval_level: 0.95,
      interval_lower: round2(value * (1 - width)),
      interval_upper: round2(value * (1 + width)),
      risk_score: s.risk_score,
      risk_state: s.risk_state,
      status: model.status,
    };
  });
}

export function latestForecastsBySlug(
  slug: string,
  symbol?: string,
  state: MockState = "ok"
): ForecastRecord[] | null {
  const model = getModel(slug);
  if (!model || !model.show_forecast) return null;
  return latestForecasts(model, symbol ?? model.markets[0], state);
}

/**
 * Historical forecasts vs realized values for coverage review. The
 * "predictions" are generated against the same mock price path so errors
 * and coverage are internally consistent.
 */
export function forecastHistory(
  slug: string,
  symbol?: string,
  state: MockState = "ok"
): ForecastHistory | null {
  const model = getModel(slug);
  if (!model || !model.show_forecast) return null;
  const sym = symbol ?? model.markets[0];
  const horizon = model.horizons.includes(5) ? 5 : model.horizons[0];
  const bars = genHistory(sym);
  const points: ForecastHistoryPoint[] = [];
  const n = 60;
  const start = bars.length - n - horizon;
  for (let i = 0; i < n; i++) {
    const at = bars[start + i];
    const realized = bars[start + i + horizon];
    const rng = mulberry32(hashSeed("fch", slug, sym, at.time));
    const noise = gaussian(rng) * 0.012 * Math.sqrt(horizon / 5);
    const predicted = realized.close * (1 + noise);
    const width = 0.02 * Math.sqrt(horizon) * (0.9 + rng() * 0.3);
    const lower = predicted * (1 - width);
    const upper = predicted * (1 + width);
    points.push({
      forecast_at: at.time,
      horizon,
      predicted: round2(predicted),
      interval_lower: round2(lower),
      interval_upper: round2(upper),
      actual: realized.close,
      error_percent: round2(((predicted - realized.close) / realized.close) * 10000) / 100,
      in_interval: realized.close >= lower && realized.close <= upper,
    });
  }
  const covered = points.filter((p) => p.in_interval).length;
  return {
    ...freshness(state),
    model_id: slug,
    symbol: sym,
    interval_level: 0.95,
    coverage: state === "empty" ? 0 : Math.round((covered / n) * 1000) / 1000,
    points: state === "empty" ? [] : points,
  };
}

const round2 = (n: number) => Math.round(n * 100) / 100;
const round3 = (n: number) => Math.round(n * 1000) / 1000;
const round4 = (n: number) => Math.round(n * 10000) / 10000;
