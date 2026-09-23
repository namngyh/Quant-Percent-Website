"""Reading and checking plugin source from the browser.

The editor added three endpoints around the existing import path. Two of them
touch the filesystem with a name that came from a browser, which is the part
worth guarding: `_safe_stem` already refuses paths, and a read handler is the
easier direction to get wrong — `../../.env` is a perfectly good filename to a
careless one, and this machine has a real .env with a database password in it.

Run:  .venv\\Scripts\\python.exe tests/test_editor_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from backend.api import routes_plugins as rp  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


INDICATOR = '''
INDICATOR = {"name": "T", "kind": "overlay", "params": [], "outputs": []}


def calculate(df, params):
    return {}
'''

STRATEGY = '''
STRATEGY = {"name": "T", "side": "both", "params": []}


def signals(df, params):
    return None
'''


@check("a path dressed as a filename is refused, not trimmed")
def _():
    # Reducing ../../.env to .env would write or read somewhere the caller did
    # not ask for and say nothing about it.
    for attempt in ("../secrets.py", "..\\\\secrets.py", "plugins/x.py", "a/../b.py"):
        try:
            rp._safe_stem(attempt)
        except HTTPException as exc:
            assert exc.status_code == 422, (attempt, exc.status_code)
        else:
            raise AssertionError(f"accepted a path: {attempt}")


@check("only plain .py names are accepted")
def _():
    assert rp._safe_stem("my_indicator.py") == "my_indicator.py"
    for bad in ("notpython.txt", "spaces here.py", "_hidden.py", ""):
        try:
            rp._safe_stem(bad)
        except HTTPException:
            pass
        else:
            raise AssertionError(f"accepted {bad!r}")


@check("the kind is read from the source, not from the caller")
def _():
    assert rp._classify(INDICATOR) == "indicator"
    assert rp._classify(STRATEGY) == "strategy"


@check("a syntax error names the line rather than failing vaguely")
def _():
    try:
        rp._classify('INDICATOR = {\n  "name": broken')
    except HTTPException as exc:
        assert exc.status_code == 422, exc.status_code
        # The line number is the whole point: "invalid syntax" alone sends the
        # user hunting through their own file.
        assert "dòng" in str(exc.detail), exc.detail
    else:
        raise AssertionError("expected a syntax error")


@check("a file claiming both kinds is refused")
def _():
    try:
        rp._classify(INDICATOR + STRATEGY)
    except HTTPException as exc:
        assert "cả INDICATOR và STRATEGY" in str(exc.detail), exc.detail
    else:
        raise AssertionError("expected a refusal")


@check("check reports the failure instead of raising it")
def _():
    """The editor calls this while typing, so half-written code is normal.

    Raising would turn every keystroke mid-edit into an error toast; the
    endpoint answers with ok=False and the reason so the editor can show it in
    place.
    """
    bad = rp.check_source(rp.CheckRequest(content="def broken(:"))
    assert bad["ok"] is False, bad
    assert bad["detail"], bad

    good = rp.check_source(rp.CheckRequest(content=INDICATOR))
    assert good == {"ok": True, "kind": "indicator"}, good


@check("check parses but never executes")
def _():
    # If this endpoint ran the source, the marker file would exist. It must
    # classify by reading the syntax tree alone.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "executed"
        source = (
            f'open({str(marker)!r}, "w").close()\n'
            'INDICATOR = {"name": "X", "kind": "overlay", "params": [], "outputs": []}\n'
            "def calculate(df, params):\n    return {}\n"
        )
        out = rp.check_source(rp.CheckRequest(content=source))
        assert out["ok"] is True, out
        assert not marker.exists(), "check executed the source"


@check("a duplicate name is refused with a code, not with a Vietnamese sentence")
def _():
    """The refusal the frontend has to recognise.

    It used to be a bare sentence, and app.js decided what it meant by looking
    for the words "đã tồn tại" in it. An English reader never sees those words,
    so the overwrite prompt never appeared and the import simply failed (§2.4).
    """
    import tempfile
    import types

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        original = rp.settings
        rp.settings = types.SimpleNamespace(plugin_indicator_dir=folder)
        try:
            first = rp.import_plugin(rp.ImportRequest(filename="dup.py", content=INDICATOR))
            assert first["path"], first

            try:
                rp.import_plugin(rp.ImportRequest(filename="dup.py", content=INDICATOR))
            except HTTPException as exc:
                assert exc.status_code == 409, exc.status_code
                assert exc.detail["code"] == "plugin_exists", exc.detail
                assert set(exc.detail["message"]) == {"vi", "en"}, exc.detail
                # The English half says the same thing, which is the whole point.
                assert "already exists" in exc.detail["message"]["en"], exc.detail
            else:
                raise AssertionError("a duplicate name was accepted")

            # And overwriting is still allowed when it is asked for.
            again = rp.import_plugin(
                rp.ImportRequest(filename="dup.py", content=INDICATOR, overwrite=True))
            assert again["path"], again
        finally:
            rp.settings = original


@check("an unknown kind is refused before it becomes a folder")
def _():
    for bad in ("indicators", "strategies", "../", "secrets"):
        try:
            rp._kind_dir(bad)
        except HTTPException as exc:
            assert exc.status_code == 422, (bad, exc.status_code)
        else:
            raise AssertionError(f"accepted kind {bad!r}")

    # And the two real ones resolve to directories.
    assert rp._kind_dir("indicator").name == "indicators"
    assert rp._kind_dir("strategy").name == "strategies"


@check("listing skips files the loaders would skip")
def _():
    # Underscore-prefixed files are not plugins; offering one for editing would
    # imply the platform loads it.
    listing = rp.list_files()
    for kind, entries in listing["files"].items():
        for entry in entries:
            assert not entry["filename"].startswith("_"), (kind, entry)
            assert entry["filename"].endswith(".py"), entry


def main() -> int:
    passed = failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
