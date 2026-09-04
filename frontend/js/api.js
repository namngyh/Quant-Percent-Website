/* Thin wrapper over the backend JSON API. */

const API = (() => {
  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      // Non-JSON body (a proxy error page, say) — fall through to the status.
    }

    if (!response.ok) {
      const detail = payload?.detail || `${response.status} ${response.statusText}`;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return payload;
  }

  const post = (path, body) =>
    request(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

  return {
    config: () => request('/api/config'),
    coverage: () => request('/api/coverage'),

    candles: ({ symbol, timeframe, limit }) => {
      const q = new URLSearchParams({ symbol, timeframe, limit: String(limit) });
      return request(`/api/candles?${q}`);
    },

    catalog: () => request('/api/indicators'),

    compute: ({ indicatorId, symbol, timeframe, params, limit }) =>
      post('/api/indicators/compute', {
        indicator_id: indicatorId,
        symbol,
        timeframe,
        params,
        limit,
      }),

    backfill: ({ symbols, timeframes } = {}) =>
      post('/api/backfill', { symbols, timeframes }),

    strategies: () => request('/api/strategies'),

    backtest: ({ strategyId, symbol, timeframe, params, limit, execution }) =>
      post('/api/strategies/backtest', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        params,
        limit,
        execution,
      }),

    optimize: ({ strategyId, symbol, timeframe, ranges, limit, metric, execution, mode, samples }) =>
      post('/api/strategies/optimize', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        ranges,
        limit,
        metric,
        execution,
        mode,
        samples,
      }),

    sweepSize: ({ ranges, bars }) =>
      post('/api/strategies/optimize/size', { ranges, bars }),
  };
})();
