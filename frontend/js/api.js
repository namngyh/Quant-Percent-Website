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
      // Non-JSON body (a proxy error page, say): fall through to the status.
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

    walkForward: ({ strategyId, symbol, timeframe, limit, ranges, metric, trainBars, testBars, execution }) =>
      post('/api/validate/walk-forward', {
        strategy_id: strategyId, symbol, timeframe, limit, ranges, metric,
        train_bars: trainBars, test_bars: testBars, execution,
      }),

    monteCarlo: ({ strategyId, symbol, timeframe, limit, params, simulations, execution }) =>
      post('/api/validate/monte-carlo', {
        strategy_id: strategyId, symbol, timeframe, limit, params, simulations, execution,
      }),

    compareStrategies: ({ entries, symbol, timeframe, limit, execution }) =>
      post('/api/validate/compare', { entries, symbol, timeframe, limit, execution }),

    report: ({ strategyId, symbol, timeframe, limit, params, execution }) =>
      post('/api/strategies/report', {
        strategy_id: strategyId, symbol, timeframe, limit, params, execution,
      }),

    statsSeries: ({ symbol, timeframe, limit }) =>
      post('/api/stats/series', { symbol, timeframe, limit }),

    statsStrategy: ({ strategyId, symbol, timeframe, limit, params, execution, nTrials }) =>
      post('/api/stats/strategy', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        limit,
        params,
        execution,
        // The number of parameter combinations behind these params. Passing it
        // is what makes the deflated Sharpe ratio mean anything.
        n_trials: nTrials || 1,
      }),

    vnSymbols: () => request('/api/markets/vn/symbols'),

    // POST even though nothing is written: the holdings are the user's own
    // position data, and keeping them out of the URL keeps them out of access
    // logs, browser history and referrer headers.
    portfolioAnalyze: ({ holdings, cash, horizonDays, lookbackDays }) =>
      post('/api/portfolio/analyze', {
        holdings, cash, horizon_days: horizonDays, lookback_days: lookbackDays,
      }),
    vnStatus: () => request('/api/markets/vn/status'),

    notifyStatus: () => request('/api/notify/status'),
    notifyTest: () => post('/api/notify/test'),
    // PUT rather than POST: saving the same settings twice must leave the same
    // state, and the browser must not be able to create a second credential.
    notifySave: ({ botToken, chatId }) =>
      request('/api/notify/settings', {
        method: 'PUT',
        body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
      }),
    notifyClear: () => request('/api/notify/settings', { method: 'DELETE' }),

    paperSessions: () => request('/api/paper'),

    paperStart: ({ strategyId, symbol, timeframe, params, execution }) =>
      post('/api/paper/start', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        params,
        execution,
      }),

    paperStop: (id) => post(`/api/paper/${id}/stop`),
    paperResume: (id) => post(`/api/paper/${id}/resume`),
    paperDelete: (id) => request(`/api/paper/${id}`, { method: 'DELETE' }),

    importPlugin: ({ filename, content, overwrite }) =>
      post('/api/plugins/import', { filename, content, overwrite }),
  };
})();
