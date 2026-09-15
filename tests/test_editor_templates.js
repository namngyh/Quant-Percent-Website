/* Load the actual editor starter files through Python's plugin loaders.
 * Run from the repository root: node tests/test_editor_templates.js
 * Files live only in a temporary directory; no user plugin is overwritten. */
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { JSDOM } = require('jsdom');

(async () => {
  const dom = new JSDOM('<body></body>', { url: 'http://localhost', runScripts: 'outside-only' });
  const { window } = dom;
  window.eval(fs.readFileSync('frontend/js/i18n.js', 'utf8') + '\n'
    + 'const API = { pluginFiles: async () => ({ files: {} }) };\n'
    + fs.readFileSync('frontend/js/editor.js', 'utf8')
    + '\nwindow.Editor = Editor; window.I18n = I18n;');
  const templates = [];
  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    for (const kind of ['indicator', 'strategy']) {
      await window.Editor.open({ kind });
      templates.push({ lang, kind, source: window.document.querySelector('[data-ed="code"]').value });
      window.Editor.close();
    }
  }
  dom.window.close();
  const python = process.env.QP_PYTHON || path.join('.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const result = execFileSync(python, ['-c', `
import json, sys, tempfile
from pathlib import Path
import pandas as pd
from backend.indicators.loader import load_plugin_file
from backend.strategy.registry import load_strategy_file

frame = pd.DataFrame({"close": range(1, 41)})
with tempfile.TemporaryDirectory() as folder:
    for template in json.loads(sys.stdin.buffer.read().decode("utf-8")):
        source = Path(folder) / (template["kind"] + "_" + template["lang"] + ".py")
        source.write_text(template["source"], encoding="utf-8")
        indicator = template["kind"] == "indicator"
        spec = (load_plugin_file if indicator else load_strategy_file)(source)
        params = spec.resolve_params({})
        assert params["length"] == 20
        if indicator:
            assert spec.kind == "overlay"
            values = spec.calculate(frame, params)["value"]
            assert values.iloc[-1] == 30.5
        else:
            values = spec.signals(frame, params)
            assert values.iloc[-1] == 1
        assert len(values) == len(frame)
        print("PASS", template["lang"], template["kind"], "starter loads and computes")
`], { input: JSON.stringify(templates), encoding: 'utf8' });
  process.stdout.write(result);
})().catch(error => { console.error(error); process.exitCode = 1; });
