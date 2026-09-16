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
      // A structured refusal — {code, message:{vi,en}} — used to be flattened
      // into JSON.stringify and shown to the user as raw braces. The message
      // is now the error text and the object is kept on the error, so callers
      // can branch on `code` and display the right language (§2.4, §3.2).
      const structured = detail && typeof detail === 'object' && !Array.isArray(detail);
      const text = typeof detail === 'string' ? detail
        : structured && detail.message ? (detail.message.vi || detail.message.en)
        : JSON.stringify(detail);
      const error = new Error(text);
      error.status = response.status;
      if (structured) {
        error.detail = detail;
        error.code = detail.code;
      }
      throw error;
    }
    return payload;
  }

  const post = (path, body) =>
    request(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

  return {
    config: () => request('/api/config'),
    coverage: () => request('/api/coverage'),

    /* One page of history older than `before` (epoch seconds).

       `end` plus `limit` returns the most recent `limit` candles at or before
       `end`, which is exactly a page going backwards. The timestamp is sent as
       a full ISO instant rather than a date, because an intraday page has to
       land on the right minute, not the right day. */
    candlesBefore: ({ symbol, timeframe, before, limit }) =>
      request(`/api/candles?${new URLSearchParams({
        symbol, timeframe, limit: String(limit),
        end: new Date((before - 1) * 1000).toISOString(),
      })}`),

    candles: ({ symbol, timeframe, limit }) => {
      const q = new URLSearchParams({ symbol, timeframe, limit: String(limit) });
      // Only sent when it is off: the server's default is to adjust, and a
      // URL that says nothing should mean the same thing everywhere.
      if (!Settings.all().data.adjustSplits) q.set('adjust', '0');
      return request(`/api/candles?${q}`);
    },

    health: () => request('/api/health'),

    // The team's own forecast, its record, the VN30 network and the ingestion
    // log — four views this platform reads but does not produce.
    teamModels: () => request('/api/markets/vn/team-models'),

    /* Where the live feed stands, asked rather than waited for.

       The socket announces a stream coming up once. A client that was not
       listening — or whose socket never opened — has to be able to ask, or it
       sits on "connecting" over a chart that is perfectly fine (§2.5). */
    liveStatus: ({ symbol, timeframe } = {}) => {
      const q = new URLSearchParams();
      if (symbol) q.set('symbol', symbol);
      if (timeframe) q.set('timeframe', timeframe);
      const query = q.toString();
      return request(`/api/live/status${query ? `?${query}` : ''}`);
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

    backtest: ({ strategyId, symbol, timeframe, params, limit, execution, period }) =>
      post('/api/strategies/backtest', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        params,
        limit,
        ...(period || {}),
        execution,
      }),

    optimize: ({ strategyId, symbol, timeframe, ranges, limit, metric, execution, mode, samples, period }) =>
      post('/api/strategies/optimize', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        ranges,
        limit,
        ...(period || {}),
        metric,
        execution,
        mode,
        samples,
      }),

    sweepSize: ({ ranges, bars }) =>
      post('/api/strategies/optimize/size', { ranges, bars }),

    walkForward: ({ strategyId, symbol, timeframe, limit, ranges, metric,
                    trainBars, testBars, purgeBars, foldMode, execution, period }) =>
      post('/api/validate/walk-forward', {
        strategy_id: strategyId, symbol, timeframe, limit, ranges, metric,
        ...(period || {}),
        train_bars: trainBars, test_bars: testBars,
        // Bars dropped between training and test, and whether the training
        // window slides or grows from bar zero.
        purge_bars: purgeBars || 0,
        fold_mode: foldMode || 'rolling',
        execution,
      }),

    monteCarlo: ({ strategyId, symbol, timeframe, limit, params, simulations, execution, period }) =>
      post('/api/validate/monte-carlo', {
        strategy_id: strategyId, symbol, timeframe, limit, params, simulations,
        ...(period || {}), execution,
      }),

    compareStrategies: ({ entries, symbol, timeframe, limit, execution, period }) =>
      post('/api/validate/compare', {
        entries, symbol, timeframe, limit, ...(period || {}), execution,
      }),

    report: ({ strategyId, symbol, timeframe, limit, params, execution, period }) =>
      post('/api/strategies/report', {
        strategy_id: strategyId, symbol, timeframe, limit, params,
        ...(period || {}), execution,
      }),

    statsSeries: ({ symbol, timeframe, limit, period }) =>
      post('/api/stats/series', { symbol, timeframe, limit, ...(period || {}) }),

    statsStrategy: ({ strategyId, symbol, timeframe, limit, params, execution,
                      nTrials, period }) =>
      post('/api/stats/strategy', {
        strategy_id: strategyId,
        symbol,
        timeframe,
        limit,
        ...(period || {}),
        params,
        execution,
        // The number of parameter combinations behind these params. Passing it
        // is what makes the deflated Sharpe ratio mean anything.
        n_trials: nTrials || 1,
      }),

    /* One strategy over several markets. Deliberately one request rather
       than a loop here: the deflated Sharpe needs to see every market's
       result at once to know how wide the search was. */
    backtestMarkets: ({ strategyId, symbols, timeframe, params, execution,
                        limit, start, end, metric }) =>
      post('/api/strategies/backtest/markets', {
        strategy_id: strategyId,
        symbols,
        timeframe,
        params,
        limit,
        start,
        end,
        metric: metric || 'sharpe',
        execution,
      }),

    pluginFiles: () => request('/api/plugins/files'),
    pluginRead: (kind, filename) =>
      request(`/api/plugins/files/${encodeURIComponent(kind)}/${encodeURIComponent(filename)}`),
    /* Parses and classifies source without writing or running it — safe to
       call on every pause in typing. */
    pluginCheck: (content) => post('/api/plugins/check', { content }),

    vnSymbols: () => request('/api/markets/vn/symbols'),
    vnCoverage: (symbol) => request(`/api/markets/vn/coverage?symbol=${encodeURIComponent(symbol)}`),

    // POST even though nothing is written: the holdings are the user's own
    // position data, and keeping them out of the URL keeps them out of access
    // logs, browser history and referrer headers.
    portfolioAnalyze: ({ holdings, cash, horizonDays, lookbackDays }) =>
      post('/api/portfolio/analyze', {
        holdings, cash, horizon_days: horizonDays, lookback_days: lookbackDays,
      }),
    vnRisk: () => request('/api/markets/vn/risk'),

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

    // Every session read as one account: combined equity, trade history and
    // a breakdown per symbol.
    paperSummary: () => request('/api/paper/summary'),

    // A hand order on a paper session. `action` is long | short | close;
    // `sizePct` is 0-1 and may be omitted to use the session's own size.
    paperOrder: (id, action, sizePct, exits) =>
      post(`/api/paper/${id}/order`, {
        action,
        size_pct: sizePct ?? null,
        stop_loss: exits?.stopLoss ?? null,
        take_profit: exits?.takeProfit ?? null,
      }),

    // Move or clear the levels on a position that is already open.
    paperExits: (id, exits) =>
      post(`/api/paper/${id}/exits`, {
        stop_loss: exits?.stopLoss ?? null,
        take_profit: exits?.takeProfit ?? null,
      }),

    paperResumeStrategy: (id) => post(`/api/paper/${id}/resume-strategy`, {}),

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
