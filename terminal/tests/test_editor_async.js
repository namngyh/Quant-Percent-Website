/* Delayed editor requests must not replace a newer file or discard new edits. */
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const tick = () => new Promise(r => setImmediate(r));

async function fixture() {
  const dom = new JSDOM('<body></body>', { url: 'http://localhost', runScripts: 'outside-only' });
  const w = dom.window;
  let scheduled;
  w.setTimeout = fn => { scheduled = fn; return 1; };
  w.clearTimeout = () => { scheduled = null; };
  const handlers = new WeakMap();
  const add = w.EventTarget.prototype.addEventListener;
  w.EventTarget.prototype.addEventListener = function(type, fn, options) {
    if (!handlers.has(this)) handlers.set(this, {});
    handlers.get(this)[type] = fn;
    return add.call(this, type, fn, options);
  };
  w.api = { pluginFiles: async () => ({ files: {} }), pluginCheck: async () => ({ ok: true, kind: 'indicator' }) };
  w.eval(fs.readFileSync('frontend/js/i18n.js', 'utf8') + '\nconst API = window.api;\n'
    + fs.readFileSync('frontend/js/editor.js', 'utf8') + '\nwindow.Editor = Editor;');
  w.Editor.init({});
  const get = key => w.document.querySelector(`[data-ed="${key}"]`);
  await w.Editor.open();
  return { w, get, check: () => scheduled(),
    save: () => handlers.get(get('save')).click(),
    edit(value) { get('code').value = value; get('code').dispatchEvent(new w.Event('input')); },
    dispose() { w.Editor.close(); dom.window.close(); } };
}

const tests = [
  ['closing during initial file listing finishes without errors', async f => {
    const pending = deferred(); f.w.api.pluginFiles = () => pending.promise;
    const opening = f.w.Editor.open(); f.w.Editor.close();
    pending.resolve({ files: {} }); await opening;
    assert.equal(f.w.document.querySelector('.editor-dialog'), null);
  }],
  ['late syntax check after close is ignored', async f => {
    const pending = deferred(); f.w.api.pluginCheck = () => pending.promise;
    const checking = f.check(); f.w.Editor.close();
    pending.resolve({ ok: true, kind: 'strategy' }); await checking;
  }],
  ['older syntax result cannot replace the latest result', async f => {
    const first = deferred(), second = deferred();
    f.w.api.pluginCheck = () => first.promise;
    const oldCheck = f.check(); f.edit('new source');
    f.w.api.pluginCheck = () => second.promise;
    const newCheck = f.check(); second.resolve({ ok: true, kind: 'indicator' }); await newCheck;
    first.resolve({ ok: true, kind: 'strategy' }); await oldCheck;
    assert.equal(f.get('kind').value, 'indicator');
  }],
  ['editing during save remains unsaved', async f => {
    const pending = deferred(); f.w.api.importPlugin = () => pending.promise;
    f.get('name').value = 'test.py'; const saving = f.save(); f.edit('new unsaved source');
    pending.resolve({ filename: 'test.py', path: 'test.py', kind: 'indicator' }); await saving;
    let prompted = false; f.w.confirm = () => { prompted = true; return false; };
    f.get('close').click(); assert.equal(prompted, true); assert.ok(f.get('code'));
  }],
  ['save completion cannot modify a newly opened editor', async f => {
    const pending = deferred(); f.w.api.importPlugin = () => pending.promise;
    f.get('name').value = 'test.py'; const saving = f.save();
    f.w.Editor.close(); await f.w.Editor.open({ kind: 'strategy' });
    pending.resolve({ filename: 'test.py', path: 'old/test.py', kind: 'indicator' }); await saving;
    assert.equal(f.get('path').textContent, ''); assert.equal(f.get('kind').value, 'strategy');
  }],
  ['repeated save while pending submits only once', async f => {
    const pending = deferred(); let calls = 0;
    f.w.api.importPlugin = () => { calls++; return pending.promise; };
    f.get('name').value = 'test.py'; const first = f.save(), second = f.save();
    pending.resolve({ filename: 'test.py', path: 'test.py', kind: 'indicator' });
    await Promise.all([first, second]); assert.equal(calls, 1);
  }],
  ['typing while a file loads prevents its late response from replacing the draft', async f => {
    const pending = deferred(); f.w.api.pluginRead = () => pending.promise;
    f.get('file').innerHTML = '<option value="old.py">old.py</option>';
    f.get('file').dispatchEvent(new f.w.Event('change'));
    f.edit('keep this draft');
    pending.resolve({ content: 'old source', filename: 'old.py', path: 'old.py' }); await tick();
    assert.equal(f.get('code').value, 'keep this draft');
  }],
  ['typing while the initial listing loads preserves the draft', async f => {
    const pending = deferred(); f.w.api.pluginFiles = () => pending.promise;
    const opening = f.w.Editor.open(); f.edit('keep initial draft');
    pending.resolve({ files: {} }); await opening;
    assert.equal(f.get('code').value, 'keep initial draft');
  }],
];
(async () => {
  let failed = 0;
  for (const [name, run] of tests) {
    const f = await fixture();
    try { await run(f); await tick(); console.log('PASS', name); }
    catch (error) { failed++; console.log('FAIL', name, error.message); }
    finally { f.dispose(); }
  }
  console.log(`${tests.length - failed} passed, ${failed} failed`);
  process.exitCode = failed ? 1 : 0;
})();
