import {
  daySeed,
  gaussian,
  hashSeed,
  mulberry32,
} from "@/lib/mock/seeded-random";
import type {
  Constituents,
  Freshness,
  History,
  MarketOverview,
  OhlcvBar,
  Quote,
  Regime,
  RiskDashboard,
  RiskState,
  StockRow,
} from "@/lib/api/types";

/**
 * Deterministic ILLUSTRATIVE market data (spec §20 mock mode).
 * None of this is real market data; every payload carries freshness
 * metadata and the UI labels it as mock.
 */

const INDEX_META: Record<string, { name: string; base: number }> = {
  VNINDEX: { name: "VN-Index", base: 1286 },
  VN30: { name: "VN30", base: 1312 },
  VN30F1M: { name: "VN30F1M", base: 1308 },
};

export const VN30_TICKERS = [
  "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
  "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
  "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
];

const REGIMES: Regime[] = [
  "bullish",
  "bullish_transition",
  "sideways",
  "bearish_transition",
  "bearish",
  "turbulent",
];
const RISK_STATES: RiskState[] = ["low", "moderate", "elevated", "high"];

/** Last completed trading day (Mon–Fri), 15:00 ICT. */
export function lastTradingDay(from = new Date()): Date {
  const d = new Date(from);
  d.setHours(15, 0, 0, 0);
  while (d.getDay() === 0 || d.getDay() === 6 || d > from) {
    d.setDate(d.getDate() - 1);
    d.setHours(15, 0, 0, 0);
  }
  return d;
}

export function tradingDaysBack(count: number, end = lastTradingDay()): Date[] {
  const days: Date[] = [];
  const d = new Date(end);
  while (days.length < count) {
    if (d.getDay() !== 0 && d.getDay() !== 6) days.unshift(new Date(d));
    d.setDate(d.getDate() - 1);
  }
  return days;
}

export type MockState = "ok" | "stale" | "empty" | "error" | "maintenance";

export function freshness(state: MockState = "ok"): Freshness {
  const asOf = lastTradingDay();
  if (state === "stale") {
    asOf.setDate(asOf.getDate() - 3);
    return {
      data_as_of: asOf.toISOString(),
      generated_at: new Date().toISOString(),
      source_status: "delayed",
      is_stale: true,
      delay_minutes: 3 * 24 * 60,
    };
  }
  return {
    data_as_of: asOf.toISOString(),
    generated_at: new Date().toISOString(),
    source_status: "ok",
    is_stale: false,
    delay_minutes: 15,
  };
}

export function genHistory(symbol: string, count = 500): OhlcvBar[] {
  const meta = INDEX_META[symbol] ?? { name: symbol, base: 60 };
  const rng = mulberry32(hashSeed("history", symbol));
  const days = tradingDaysBack(count);
  const bars: OhlcvBar[] = [];
  // Walk backwards-planned drift so the series ends near the base price
  let price = meta.base * (0.82 + rng() * 0.1);
  const dailyVol = 0.011;
  const drift = Math.log(meta.base / price) / count;
  for (const day of days) {
    const r = drift + gaussian(rng) * dailyVol;
    const open = price;
    const close = price * Math.exp(r);
    const hi = Math.max(open, close) * (1 + rng() * 0.006);
    const lo = Math.min(open, close) * (1 - rng() * 0.006);
    bars.push({
      time: day.toISOString().slice(0, 10),
      open: round2(open),
      high: round2(hi),
      low: round2(lo),
      close: round2(close),
      volume: Math.round(180_000_000 * (0.6 + rng() * 0.9)),
    });
    price = close;
  }
  return bars;
}

function round2(n: number) {
  return Math.round(n * 100) / 100;
}

export function getQuote(symbol: string, state: MockState = "ok"): Quote {
  const meta = INDEX_META[symbol] ?? { name: symbol, base: 60 };
  const bars = genHistory(symbol);
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  return {
    ...freshness(state),
    symbol,
    name: meta.name,
    price: last.close,
    change: round2(last.close - prev.close),
    change_percent: round2(((last.close - prev.close) / prev.close) * 10000) / 100,
    volume: last.volume,
    currency: "VND",
  };
}

export function getHistory(
  symbol: string,
  count = 250,
  state: MockState = "ok"
): History {
  const bars = state === "empty" ? [] : genHistory(symbol).slice(-count);
  return { ...freshness(state), symbol, timeframe: "1D", bars };
}

/** Today's market-level state, stable for the whole day. */
export function marketState() {
  const rng = mulberry32(hashSeed("state", daySeed()));
  const regimeIdx = Math.floor(rng() * 2.4); // biased to the calmer states
  const regime = REGIMES[regimeIdx];
  // Probability broadly consistent with the regime
  const probUp = 0.6 - regimeIdx * 0.05 + (rng() - 0.5) * 0.08;
  const vol = 0.12 + rng() * 0.07;
  const riskScore = Math.round(25 + rng() * 40);
  const riskState =
    RISK_STATES[Math.min(3, Math.floor(riskScore / 25))] ?? "moderate";
  return {
    regime,
    regime_probability: round2(0.55 + rng() * 0.3),
    probability_up: round2(Math.min(0.85, Math.max(0.15, probUp)) * 1000) / 1000,
    volatility: round2(vol * 1000) / 1000,
    risk_score: riskScore,
    risk_state: riskState,
    model_consensus: round2(0.5 + rng() * 0.4),
  };
}

export function getOverview(state: MockState = "ok"): MarketOverview {
  const s = marketState();
  const signal =
    s.risk_state === "high"
      ? "high_risk"
      : s.regime === "turbulent"
        ? "defensive"
        : s.probability_up > 0.58
          ? "bullish"
          : s.probability_up < 0.45
            ? "defensive"
            : s.model_consensus < 0.6
              ? "low_conviction"
              : "neutral";
  return {
    ...freshness(state),
    quotes:
      state === "empty"
        ? []
        : Object.keys(INDEX_META).map((sym) => getQuote(sym, state)),
    regime: s.regime,
    regime_probability: s.regime_probability,
    probability_up: s.probability_up,
    probability_down: round2((1 - s.probability_up) * 1000) / 1000,
    volatility: s.volatility,
    risk_state: s.risk_state,
    risk_score: s.risk_score,
    model_consensus: s.model_consensus,
    public_signal: signal,
  };
}

export function getConstituents(state: MockState = "ok"): Constituents {
  if (state === "empty") return { ...freshness(state), rows: [] };
  const dayRng = mulberry32(hashSeed("stocks", daySeed()));
  const scored = VN30_TICKERS.map((ticker) => {
    const rng = mulberry32(hashSeed("stock", ticker, daySeed()));
    const base = 20 + mulberry32(hashSeed("base", ticker))() * 90;
    const change = (rng() - 0.48) * 4;
    const probUp = Math.min(0.82, Math.max(0.18, 0.5 + (rng() - 0.5) * 0.5));
    const vol = 0.16 + rng() * 0.22;
    const riskState =
      RISK_STATES[Math.min(3, Math.floor(rng() * 4 * (vol / 0.3)))] ?? "moderate";
    const regime = REGIMES[Math.floor(rng() * REGIMES.length)];
    const score = probUp * 2 - vol + dayRng() * 0.2;
    return {
      ticker,
      price: round2(base * (1 + change / 100)),
      change_percent: round2(change * 100) / 100,
      regime,
      probability_up: round2(probUp * 1000) / 1000,
      volatility: round2(vol * 1000) / 1000,
      risk_state: riskState,
      score,
    };
  });
  scored.sort((a, b) => b.score - a.score);
  const rows: StockRow[] = scored.map((s, i) => ({
    ticker: s.ticker,
    price: s.price,
    change_percent: s.change_percent,
    regime: s.regime,
    probability_up: s.probability_up,
    volatility: s.volatility,
    risk_state: s.risk_state,
    rank: i + 1,
  }));
  rows.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return { ...freshness(state), rows };
}

export function getRiskDashboard(state: MockState = "ok"): RiskDashboard {
  const s = marketState();
  const rng = mulberry32(hashSeed("risk", daySeed()));
  const buckets = Array.from({ length: 12 }, (_, i) => -(i + 1) * 0.02);
  let remaining = 1;
  const dist = buckets.map((bucket, i) => {
    const p =
      i === buckets.length - 1
        ? remaining
        : remaining * (0.32 + rng() * 0.12) * (i < 3 ? 1 : 0.85);
    remaining -= p;
    return { bucket: round2(bucket * 100) / 100, probability: round2(p * 1000) / 1000 };
  });
  return {
    ...freshness(state),
    current_drawdown: -round2((0.02 + rng() * 0.05) * 1000) / 1000,
    rolling_drawdown_60d: -round2((0.04 + rng() * 0.06) * 1000) / 1000,
    volatility: s.volatility,
    var_95: -round2((0.012 + rng() * 0.01) * 1000) / 1000,
    es_95: -round2((0.02 + rng() * 0.014) * 1000) / 1000,
    downside_probability: round2((1 - s.probability_up) * 1000) / 1000,
    risk_state: s.risk_state,
    mc_drawdown_distribution: state === "empty" ? [] : dist,
    mc_paths: 10000,
    stress_scenarios:
      state === "empty"
        ? []
        : [
            { id: "vol_shock", impact_percent: -round2((6 + rng() * 4) * 100) / 100 },
            { id: "gap_down", impact_percent: -round2((4 + rng() * 3) * 100) / 100 },
            { id: "liquidity_drought", impact_percent: -round2((3 + rng() * 3) * 100) / 100 },
            { id: "regime_flip", impact_percent: -round2((2 + rng() * 3) * 100) / 100 },
          ],
  };
}
