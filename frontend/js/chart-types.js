/* The price series, in the twelve shapes a chart can take.
 *
 * Lightweight Charts 4.2.3 ships five series kinds — candlestick, bar, line,
 * area, baseline, histogram — and the menu asks for twelve. The rest are those
 * five configured or fed differently, which is worth writing down once because
 * the derivations are not obvious from the library's API:
 *
 *   hollow candles  a candlestick series whose *up* bodies are transparent, so
 *                   the border alone draws them. Down bodies stay filled: the
 *                   convention exists so a rising bar reads as empty and a
 *                   falling one as solid, not so both become outlines.
 *   step line       a line series with `lineType: 1` (WithSteps).
 *   markers line    a line series with `pointMarkersVisible`.
 *   HLC area        three series, not one: an area for the close and two thin
 *                   lines for the session high and low. The library has no
 *                   band primitive, so the band is drawn as its edges.
 *   columns         a histogram of closes on the price scale, which is a
 *                   different thing from the volume histogram below it.
 *   high-low        a bar series with `openVisible: false`, leaving the wick
 *                   between high and low and the close tick.
 *   Heikin Ashi     candles computed from the OHLC rather than styled: the
 *                   smoothing is in the data, so it is derived here and fed to
 *                   an ordinary candlestick series.
 *
 * Every type reads the same `candles` array, so switching is a redraw and
 * never a refetch, and the time scale the user is looking at is preserved by
 * the caller.
 */

const ChartTypes = (() => {
  // Market colours, matching frontend/styles.css. Kept here rather than read
  // from CSS because the chart paints to a canvas and cannot use a variable.
  const UP = '#089981';
  const DOWN = '#f23645';

  /* The catalogue. `id` is stored in localStorage and sent nowhere, so it is a
     stable key; `label` is a function so it follows the language switch. */
  const TYPES = [
    { id: 'bars', icon: 'bars', label: () => L('Hình thanh', 'Bars') },
    { id: 'candles', icon: 'candles', label: () => L('Biểu đồ nến', 'Candles') },
    { id: 'hollow', icon: 'hollow', label: () => L('Nến rỗng', 'Hollow candles') },
    { id: 'line', icon: 'line', label: () => L('Đường thẳng', 'Line') },
    { id: 'line_markers', icon: 'line-markers', label: () => L('Đường có điểm đánh dấu', 'Line with markers') },
    { id: 'step', icon: 'step', label: () => L('Đường bậc', 'Step line') },
    { id: 'area', icon: 'area', label: () => L('Biểu đồ vùng', 'Area') },
    { id: 'hlc_area', icon: 'hlc', label: () => L('Vùng HLC', 'HLC area') },
    { id: 'baseline', icon: 'baseline', label: () => L('Đường cơ sở', 'Baseline') },
    { id: 'columns', icon: 'columns', label: () => L('Các cột', 'Columns') },
    { id: 'high_low', icon: 'highlow', label: () => L('Đỉnh–Đáy', 'High-Low') },
    { id: 'heikin_ashi', icon: 'heikin', label: () => L('Heikin Ashi', 'Heikin Ashi') },
  ];

  const byId = new Map(TYPES.map((t) => [t.id, t]));
  const has = (id) => byId.has(id);

  /* Heikin Ashi.
   *
   *   close = (O + H + L + C) / 4
   *   open  = (previous HA open + previous HA close) / 2
   *   high  = max(H, HA open, HA close)
   *   low   = min(L, HA open, HA close)
   *
   * The first bar has no previous HA candle, so it seeds from its own open and
   * close. That seed decays within a few bars; seeding from zero would put a
   * spike at the left edge that looks like real data. */
  function heikinAshi(candles) {
    const out = new Array(candles.length);
    let prevOpen = null;
    let prevClose = null;
    for (let i = 0; i < candles.length; i += 1) {
      const c = candles[i];
      const close = (c.open + c.high + c.low + c.close) / 4;
      const open = prevOpen === null
        ? (c.open + c.close) / 2
        : (prevOpen + prevClose) / 2;
      out[i] = {
        time: c.time,
        open,
        close,
        high: Math.max(c.high, open, close),
        low: Math.min(c.low, open, close),
      };
      prevOpen = open;
      prevClose = close;
    }
    return out;
  }

  /* Build the series a type needs, and return how to feed them.
   *
   * Returns `{ series: [...], apply(candles) }`. The caller owns removal: a
   * type change removes what the previous type made before asking for this.
   * `series[0]` is the one that carries the price line and the last value. */
  function build(chart, typeId) {
    const type = byId.get(typeId) || byId.get('candles');

    switch (type.id) {
      case 'bars':
        return single(chart.addBarSeries({
          upColor: UP, downColor: DOWN, thinBars: false,
        }), (c) => c);

      case 'high_low':
        // No open tick: the mark is the high-low span plus the close.
        return single(chart.addBarSeries({
          upColor: UP, downColor: DOWN, thinBars: true, openVisible: false,
        }), (c) => c);

      case 'hollow': {
        const s = chart.addCandlestickSeries({
          upColor: 'rgba(0,0,0,0)',
          downColor: DOWN,
          borderUpColor: UP,
          borderDownColor: DOWN,
          wickUpColor: UP,
          wickDownColor: DOWN,
        });
        return single(s, (c) => c);
      }

      case 'heikin_ashi':
        return single(chart.addCandlestickSeries({
          upColor: UP, downColor: DOWN,
          borderUpColor: UP, borderDownColor: DOWN,
          wickUpColor: UP, wickDownColor: DOWN,
        }), heikinAshi);

      case 'line':
        return single(chart.addLineSeries({ color: UP, lineWidth: 2 }), closes);

      case 'line_markers':
        return single(chart.addLineSeries({
          color: UP, lineWidth: 2, pointMarkersVisible: true,
          pointMarkersRadius: 3,
        }), closes);

      case 'step':
        // LineType.WithSteps === 1. The enum is not exported on the global in
        // this build, so the numeric value is used with its name written here.
        return single(chart.addLineSeries({
          color: UP, lineWidth: 2, lineType: 1,
        }), closes);

      case 'area':
        return single(chart.addAreaSeries({
          lineColor: UP, lineWidth: 2,
          topColor: 'rgba(8, 153, 129, 0.28)',
          bottomColor: 'rgba(8, 153, 129, 0.02)',
        }), closes);

      case 'baseline': {
        /* The baseline is the first close of the window, so the shading says
           "up or down since the left edge of what you are looking at" — the
           same question the header's percentage answers. A fixed price would
           make the colours depend on a number the user cannot see. */
        const s = chart.addBaselineSeries({
          topLineColor: UP,
          topFillColor1: 'rgba(8, 153, 129, 0.28)',
          topFillColor2: 'rgba(8, 153, 129, 0.02)',
          bottomLineColor: DOWN,
          bottomFillColor1: 'rgba(242, 54, 69, 0.02)',
          bottomFillColor2: 'rgba(242, 54, 69, 0.28)',
          lineWidth: 2,
        });
        return {
          series: [s],
          apply(candles) {
            s.applyOptions({
              baseValue: { type: 'price', price: candles.length ? candles[0].close : 0 },
            });
            s.setData(closes(candles));
          },
          update: (candle) => s.update({ time: candle.time, value: candle.close }),
        };
      }

      case 'columns':
        return single(chart.addHistogramSeries({ color: UP }), (candles) =>
          candles.map((c, i) => ({
            time: c.time,
            value: c.close,
            // Coloured against the previous close, which is what makes a column
            // chart readable: a column's height is the price, so direction has
            // to come from somewhere else.
            color: i > 0 && c.close < candles[i - 1].close ? DOWN : UP,
          })));

      case 'hlc_area': {
        const close = chart.addAreaSeries({
          lineColor: UP, lineWidth: 2,
          topColor: 'rgba(8, 153, 129, 0.22)',
          bottomColor: 'rgba(8, 153, 129, 0.02)',
        });
        const high = chart.addLineSeries({
          color: 'rgba(8, 153, 129, 0.45)', lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false,
        });
        const low = chart.addLineSeries({
          color: 'rgba(242, 54, 69, 0.45)', lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false,
        });
        return {
          series: [close, high, low],
          apply(candles) {
            close.setData(closes(candles));
            high.setData(candles.map((c) => ({ time: c.time, value: c.high })));
            low.setData(candles.map((c) => ({ time: c.time, value: c.low })));
          },
          // All three edges move on a live bar, or the band would lag its own
          // centre line by one candle.
          update(candle) {
            close.update({ time: candle.time, value: candle.close });
            high.update({ time: candle.time, value: candle.high });
            low.update({ time: candle.time, value: candle.low });
          },
        };
      }

      case 'candles':
      default:
        return single(chart.addCandlestickSeries({
          upColor: UP, downColor: DOWN,
          borderUpColor: UP, borderDownColor: DOWN,
          wickUpColor: UP, wickDownColor: DOWN,
        }), (c) => c);
    }
  }

  const closes = (candles) => candles.map((c) => ({ time: c.time, value: c.close }));

  function single(series, shape) {
    return {
      series: [series],
      apply: (candles) => series.setData(shape(candles)),
      update: (candle, prev, typeId) => series.update(pointFor(typeId, candle, prev)),
    };
  }

  /* One bar's worth of an update, in whatever shape the type wants.
   *
   * Heikin Ashi is the exception and says so: its open depends on the previous
   * HA candle, which a single point does not carry, so a live tick on an HA
   * chart is approximated from the raw bar. It settles to the exact value on
   * the next full redraw. Reporting that is better than a smoothed chart whose
   * last candle is quietly of a different kind. */
  function pointFor(typeId, candle, previousCandles) {
    const t = byId.get(typeId)?.id || 'candles';
    if (t === 'line' || t === 'line_markers' || t === 'step'
        || t === 'area' || t === 'baseline') {
      return { time: candle.time, value: candle.close };
    }
    if (t === 'columns') {
      const prev = previousCandles?.[previousCandles.length - 1];
      return {
        time: candle.time,
        value: candle.close,
        color: prev && candle.close < prev.close ? DOWN : UP,
      };
    }
    if (t === 'heikin_ashi') {
      const prev = previousCandles?.[previousCandles.length - 1];
      const close = (candle.open + candle.high + candle.low + candle.close) / 4;
      const open = prev ? (prev.open + prev.close) / 2 : (candle.open + candle.close) / 2;
      return {
        time: candle.time, open, close,
        high: Math.max(candle.high, open, close),
        low: Math.min(candle.low, open, close),
      };
    }
    return candle;
  }

  return {
    get list() { return TYPES.slice(); },
    has,
    build,
    pointFor,
    heikinAshi,
    label: (id) => (byId.get(id) || byId.get('candles')).label(),
    icon: (id) => (byId.get(id) || byId.get('candles')).icon,
  };
})();
