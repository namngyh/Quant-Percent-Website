"""Bilingual text for anything the backend writes in prose.

Most of what this platform returns is numbers, and numbers need no
translation. But the statistical tests, the backtest report and the portfolio
panel all return *sentences* — a conclusion, the assumptions a test stands on,
a caveat on a simulation — and those are the part a reader actually acts on.
Leaving them in one language would mean the English interface still explains
itself in Vietnamese exactly where the explanation matters most.

The shape is a pair, not a lookup:

    bi("Bác bỏ chuẩn tính.", "Normality is rejected.")
    -> {"vi": "Bác bỏ chuẩn tính.", "en": "Normality is rejected."}

and the browser picks with `I18n.pick`. Three consequences, all deliberate:

* **Both languages ship in every response.** Switching language re-renders
  from data already in hand rather than refetching, so the toggle is instant
  and works on a result computed minutes ago.
* **No language is threaded through the request.** Nothing in the analysis
  layer has to know who is reading, which keeps `lang` out of a dozen function
  signatures that are otherwise about mathematics.
* **The two halves sit on the same line.** A key-based catalogue puts the
  translation somewhere else, and the two drift the first time one is edited
  without the other. Here that is not possible without seeing both.

Cost: a report payload roughly 15% larger. On a 200 KB response served over
localhost, that is not a trade worth thinking about.
"""

from __future__ import annotations

# A translated string, as it appears in a JSON payload.
Text = dict[str, str]


def bi(vi: str, en: str) -> Text:
    """One string in both languages."""
    return {"vi": vi, "en": en}


def plain(value: str | Text | None) -> str:
    """The Vietnamese form, for logs and tests that assert on wording.

    Anything reaching the browser goes through `I18n.pick` instead; this exists
    so a `bi()` value can still be printed or matched on the Python side
    without every call site learning the pair shape.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        return value.get("vi") or value.get("en") or ""
    return value
