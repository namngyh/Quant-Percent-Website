/* Run the existing browser probes in isolated Chrome contexts.
 * Start the app and a headless Chrome with --remote-debugging-port=9223, then:
 *   node tests/run_browser_probes.js panels charttype pickerflip
 * Requires Node 22+ (built-in fetch and WebSocket). No npm dependency.
 */
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const endpoint = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9223';
  const app = process.env.QP_TEST_URL || 'http://127.0.0.1:8000';
  const version = await (await fetch(`${endpoint}/json/version`)).json();
  const socket = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  const errors = new Map();
  const testPages = new Map();
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (pending.has(message.id)) {
      const { resolve, reject, timer } = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(timer);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') {
      errors.get(message.sessionId)?.push(message.params.exceptionDetails.exception?.description
        || message.params.exceptionDetails.text);
    } else if (message.method === 'Page.javascriptDialogOpening') {
      errors.get(message.sessionId)?.push(`Unexpected ${message.params.type}: ${message.params.message}`);
      send('Page.handleJavaScriptDialog', { accept: false }, message.sessionId).catch(() => {});
    } else if (message.method === 'Fetch.requestPaused') {
      send('Fetch.fulfillRequest', {
        requestId: message.params.requestId, responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }],
        body: testPages.get(message.sessionId),
      }, message.sessionId).catch(error => errors.get(message.sessionId)?.push(error.message));
    }
  });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const requestId = ++id;
    const timer = setTimeout(() => {
      pending.delete(requestId);
      reject(new Error(`Timed out: ${method}`));
    }, 20000);
    pending.set(requestId, { resolve, reject, timer });
    socket.send(JSON.stringify({ id: requestId, method, params, sessionId }));
  });
  const groups = process.argv.slice(2);
  if (!groups.length) groups.push('async', 'multichart', 'resize', 'persist', 'tools');
  const completed = output => /DONE|\d+ failed|all .+ passed|(?:checks?|guards|level drag) holds?/i.test(output);
  let failures = 0;
  try {
    for (const group of groups) {
      const { browserContextId } = await send('Target.createBrowserContext');
      try {
        const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
        const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
        errors.set(sessionId, []);
        await send('Runtime.enable', {}, sessionId);
        await send('Page.enable', {}, sessionId);
        await send('Emulation.setDeviceMetricsOverride', {
          width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false,
        }, sessionId);
        if (['types', 'guards', 'layout', 'selfcheck', 'settings', 'levels'].includes(group)) {
          // Existing HTML tests use /static assets and need the app's origin.
          const filename = { types: 'test_chart_types.html', guards: 'test_chart_guards.html',
            layout: 'test_chart_layout.html', selfcheck: 'test_chart_selfcheck.html',
            settings: 'test_settings_ui.html', levels: 'test_level_drag.html' }[group];
          testPages.set(sessionId, fs.readFileSync(path.join(__dirname, filename)).toString('base64'));
          await send('Fetch.enable', {
            patterns: [{ urlPattern: `${app}/__browser_test__`, requestStage: 'Request' }],
          }, sessionId);
          await send('Page.navigate', { url: `${app}/__browser_test__` }, sessionId);
        } else {
          await send('Page.navigate', { url: `${app}/static/_probe.html?only=${encodeURIComponent(group)}` }, sessionId);
        }
        let output = '';
        const deadline = Date.now() + 180000;
        while (Date.now() < deadline) {
          const response = await send('Runtime.evaluate', {
            expression: 'document.getElementById("out")?.textContent || ""', returnByValue: true,
          }, sessionId);
          output = response.result?.value || '';
          if (completed(output) || /PROBE ERROR:/i.test(output) || errors.get(sessionId).length) break;
          await new Promise(resolve => setTimeout(resolve, 500));
        }
        const complete = completed(output);
        const failed = !complete || /\bFAIL\b|\bLOI:|KHONG nap|[1-9]\d* failed/i.test(output)
          || errors.get(sessionId).length > 0;
        if (failed) failures++;
        console.log(`\n${failed ? 'FAIL' : 'PASS'} ${group}\n${output}`);
        for (const error of errors.get(sessionId)) console.log(`BROWSER ERROR: ${error}`);
        if (!complete) console.log('TIMEOUT: probe did not finish');
      } finally {
        await send('Target.disposeBrowserContext', { browserContextId });
      }
    }
  } finally {
    socket.close();
  }
  console.log(`\n${groups.length - failures} groups passed, ${failures} failed`);
  process.exitCode = failures ? 1 : 0;
}

main().catch(error => { console.error(error); process.exitCode = 1; });
