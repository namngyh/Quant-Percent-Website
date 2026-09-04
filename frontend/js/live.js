/* The live channel: streaming candles and plugin hot-reload.

   One WebSocket carries both. It reconnects on its own with backoff, because
   a research tool left open overnight will lose its connection at some point
   and should recover without anyone noticing. */

const Live = (() => {
  const RECONNECT_BASE_MS = 1000;
  const RECONNECT_MAX_MS = 30000;

  let socket = null;
  let enabled = false;
  let reconnectDelay = RECONNECT_BASE_MS;
  let reconnectTimer = null;
  let desired = null; // { symbol, timeframe } we want to be subscribed to

  const handlers = {
    onCandle: () => {},
    onCandleClose: () => {},
    onPluginsChanged: () => {},
    onStatus: () => {},
    onPaperUpdate: () => {},
    onPaperEvent: () => {},
  };

  function url() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${location.host}/ws/live`;
  }

  function open() {
    if (!enabled || socket) return;

    socket = new WebSocket(url());

    socket.addEventListener('open', () => {
      reconnectDelay = RECONNECT_BASE_MS;
      handlers.onStatus({ state: 'connecting' });
      if (desired) send({ action: 'subscribe', ...desired });
    });

    socket.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      route(message);
    });

    socket.addEventListener('close', () => {
      socket = null;
      handlers.onStatus({ state: 'offline' });
      scheduleReconnect();
    });

    socket.addEventListener('error', () => {
      // 'close' always follows, and that is where reconnection is handled.
      if (socket) socket.close();
    });
  }

  function route(message) {
    switch (message.type) {
      case 'candle':
        // Ignore anything for a series we are no longer looking at: an
        // unsubscribe and an in-flight message can cross.
        if (
          desired &&
          (message.symbol !== desired.symbol || message.timeframe !== desired.timeframe)
        ) {
          return;
        }
        handlers.onCandle(message);
        if (message.closed) handlers.onCandleClose(message);
        break;

      case 'stream_status':
        handlers.onStatus({ state: message.connected ? 'live' : 'offline', ...message });
        break;

      case 'plugins_changed':
        handlers.onPluginsChanged(message.kind);
        break;

      // Paper sessions run server-side and push their own updates, so the
      // panel reflects a fill the moment it happens rather than on a poll.
      case 'paper_update':
        handlers.onPaperUpdate(message.session);
        break;

      case 'paper_event':
        handlers.onPaperEvent(message.session_id, message.event);
        break;

      case 'error':
        handlers.onStatus({ state: 'error', message: message.message });
        break;

      default:
        break;
    }
  }

  function scheduleReconnect() {
    if (!enabled || reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
  }

  function send(payload) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    }
  }

  function close() {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
    if (socket) {
      const s = socket;
      socket = null; // stop the close handler from reconnecting
      s.close();
    }
  }

  // ---------- Public ----------

  function init(config) {
    Object.assign(handlers, config);
  }

  function setEnabled(on) {
    enabled = on;
    if (on) {
      open();
    } else {
      close();
      handlers.onStatus({ state: 'off' });
    }
  }

  function subscribe(symbol, timeframe) {
    desired = { symbol, timeframe };
    if (!enabled) return;
    if (socket && socket.readyState === WebSocket.OPEN) {
      send({ action: 'subscribe', symbol, timeframe });
    } else {
      open();
    }
  }

  return { init, setEnabled, subscribe, get enabled() { return enabled; } };
})();
