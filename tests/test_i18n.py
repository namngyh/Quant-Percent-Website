"""Every user-visible string exists in both languages.

The interface is bilingual by construction: backend prose travels as a
``bi(vi, en)`` pair, and a frontend string used once is written inline as
``L('tiếng Việt', 'English')``. Neither convention is enforced by anything, so
a string added in a hurry as a bare Vietnamese literal renders identically in
both languages and nothing complains — which is exactly what kept happening.

``tests/test_render.js`` catches the panels it renders. This catches the rest:
toasts, status lines, dialog text, tooltips set from script, and any panel the
render test does not reach.

How it decides. The file is walked once, tracking two things: whether the
cursor is inside a comment (comments may be in either language) and whether it
is inside the *first* argument of an ``L(`` call or after a ``vi:`` key, which
are the two places Vietnamese belongs. Everything else that carries a
Vietnamese diacritic is a string with no English twin.

Run:  .venv\\Scripts\\python.exe tests/test_i18n.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VIET = re.compile(
    '[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị'
    'òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', re.I)

# Names that carry the same diacritics Vietnamese does and are spelled that way
# in English too. Without this the English half of a pair citing Cramér or
# López de Prado is reported as untranslated Vietnamese.
NAMES = re.compile('|'.join([
    'Cramér', 'López', 'Székely', 'Politis', 'Ljung', 'Doornik',
    'Anis', "D'Agostino", 'Ané',
]))

# Files whose Vietnamese is the dictionary itself, or is not user-visible.
SKIP = {'i18n.js'}

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def untranslated(source: str) -> list[tuple[int, str]]:
    """Vietnamese string literals with no English twin, as (line, text)."""
    out: list[tuple[int, str]] = []
    i, line = 0, 1
    n = len(source)
    # Depth of the L( call we are inside, and whether we are still in its first
    # argument. Vietnamese is expected there and nowhere else.
    l_depth: list[int] = []
    depth = 0
    in_vi_value = False

    while i < n:
        ch = source[i]

        if ch == '\n':
            line += 1
            i += 1
            in_vi_value = False
            continue

        # Comments.
        if ch == '/' and i + 1 < n:
            if source[i + 1] == '/':
                while i < n and source[i] != '\n':
                    i += 1
                continue
            if source[i + 1] == '*':
                end = source.find('*/', i + 2)
                end = n if end == -1 else end + 2
                line += source.count('\n', i, end)
                i = end
                continue

        # `L(` opens a place where Vietnamese belongs, until its first comma.
        if ch == 'L' and source[i + 1:i + 2] == '(' and (i == 0 or not source[i - 1].isalnum()):
            l_depth.append(depth)
            depth += 1
            i += 2
            continue
        if ch == 'v' and source[i:i + 3] == 'vi:':
            in_vi_value = True
            i += 3
            continue
        # A citation is the same text in both languages, and academic names
        # carry the same diacritics Vietnamese does — "López de Prado" was
        # being reported as an untranslated string.
        if source[i:i + 7] == 'source:':
            in_vi_value = True
            i += 7
            continue

        if ch in '([{':
            depth += 1
            i += 1
            continue
        if ch in ')]}':
            depth -= 1
            if l_depth and depth <= l_depth[-1]:
                l_depth.pop()
            i += 1
            continue
        if ch == ',' and l_depth and depth == l_depth[-1] + 1:
            # Past the first argument of this L(...): English from here.
            l_depth[-1] = -999
            i += 1
            continue

        if ch in '\'"`':
            quote = ch
            start_line = line
            j = i + 1
            buf = []
            while j < n:
                if source[j] == '\\':
                    buf.append(source[j:j + 2])
                    j += 2
                    continue
                if source[j] == quote:
                    break
                # A `${...}` hole in a template literal is code, not text.
                # Without this, a template containing `${L('a', 'b')}` reads as
                # one long Vietnamese string and is reported, while a genuinely
                # bare literal in the same hole would be missed — the scanner
                # would be wrong in both directions at once.
                if quote == '`' and source[j] == '$' and source[j + 1:j + 2] == '{':
                    k, hole = j + 2, 1
                    while k < n and hole:
                        if source[k] == '{':
                            hole += 1
                        elif source[k] == '}':
                            hole -= 1
                        elif source[k] == '\n':
                            line += 1
                        k += 1
                    # Only when the template itself is not already inside a
                    # place where Vietnamese belongs. `L(`...${x ? 'MUA' :
                    # 'BÁN'}...`, `...`)` is one Vietnamese argument; recursing
                    # without carrying that context reported its own ternary
                    # branches as untranslated.
                    if not (in_vi_value or (l_depth and l_depth[-1] != -999)):
                        for off, found in untranslated(source[j + 2:k - 1]):
                            out.append((line + off - 1, found))
                    j = k
                    continue
                if source[j] == '\n':
                    line += 1
                    if quote != '`':
                        break
                buf.append(source[j])
                j += 1
            text = ''.join(buf)
            # A quoted object key is an identifier, not display text. The
            # portfolio panel keys its risk grades by the Vietnamese word the
            # API returns on purpose, so the payload does not change shape
            # depending on who is looking at it.
            after = source[j + 1:j + 3].lstrip()
            is_key = after.startswith(':')
            protected = is_key or in_vi_value or (l_depth and l_depth[-1] != -999)
            if VIET.search(NAMES.sub('', text)) and not protected:
                out.append((start_line, ' '.join(text.split())[:90]))
            i = j + 1
            continue

        i += 1

    return out


@check("the scanner recognises where Vietnamese is allowed")
def _():
    # A pair, a dictionary entry and a comment are all fine.
    ok = """
    const a = L('Xin chào', 'Hello');
    const b = { vi: 'Xin chào', en: 'Hello' };
    // Xin chào
    /* Xin chào */
    """
    assert untranslated(ok) == [], untranslated(ok)

    # A bare literal, and the English half of a pair left in Vietnamese, are not.
    bad = """
    onToast('Đã xong');
    const c = L('Đã xong', 'Đã xong');
    """
    found = [text for _line, text in untranslated(bad)]
    assert len(found) == 2, found
    assert 'Đã xong' in found[0], found


# A ratchet, not a clean bill of health. Every file below is bilingual; app.js
# still holds two blocks of untranslated prose — the plugin-format help and the
# Telegram setup notes. Recording the number here rather than skipping the file
# keeps the debt visible, stops it growing, and shrinks to nothing by lowering
# this line. Set it to 0 and delete the entry when app.js is finished.
BUDGET = {'app.js': 97}


@check("no file gains an untranslated string, and the remaining debt does not grow")
def _():
    counts: dict[str, list[tuple[int, str]]] = {}
    for path in sorted((ROOT / 'frontend' / 'js').glob('*.js')):
        if path.name in SKIP:
            continue
        hits = untranslated(io.open(path, encoding='utf-8').read())
        if hits:
            counts[path.name] = hits

    problems = []
    for name, hits in counts.items():
        allowed = BUDGET.get(name, 0)
        if len(hits) > allowed:
            problems.append(f'{name}: {len(hits)} untranslated, budget {allowed}')
            for ln, text in hits[:6]:
                problems.append(f'    line {ln}: {text}')
            if len(hits) > 6:
                problems.append(f'    ... and {len(hits) - 6} more')

    # A budget that is no longer needed should be lowered, not left to rot.
    for name, allowed in BUDGET.items():
        actual = len(counts.get(name, []))
        if actual < allowed:
            problems.append(
                f'{name}: down to {actual}; lower BUDGET to {actual} '
                f'(or drop the entry) to keep the ratchet tight')

    if problems:
        raise AssertionError('\n          '.join(problems))


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
