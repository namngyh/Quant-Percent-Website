"""Splits and stock dividends, inferred from the prices themselves.

`api.v_history_1d` returns **raw** prices: a share that split two-for-one prints
half the price the next session, with nothing in the schema to say why. Measured
on the real data: 540 such steps across 320 of 1 533 symbols in 400 sessions
(§3.6 of CLAUDE.md). A backtest running through one of them sees a −50% crash
that never happened, and sells, stops out, or is liquidated on it.

The schema carries no corporate-action history, so this module does not look one
up. It uses the one fact the market itself guarantees: **a price band**. HOSE
allows 7% a session, HNX 10%, UPCOM 15%. A single session past 20% is therefore
not a market move — it is the instrument being redenominated — and the size of
the step is the ratio.

What this cannot do, said plainly (§2.7):

* **Ordinary cash dividends are invisible here.** A 3% dividend drops the price
  3%, well inside the band, and no rule on prices alone can tell it from a bad
  afternoon. Total-return series need a dividend history this database does not
  have. What is corrected here is the class of event that moves a price further
  than the exchange allows: splits, stock dividends, large one-off distributions.
* The ratio is **inferred**, not looked up. It is the exact step the prices took,
  which is what makes the series continuous; `ratio_label` names the tidy
  fraction when there is one, and says nothing when there is not.
* A trading halt spanning a real collapse would look like an event. On a banded
  exchange a collapse arrives as a run of floor sessions, not as one step, so
  this is rare — but it is the failure mode to remember.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import pandas as pd

# The widest band in this market is UPCOM's 15%. 20% leaves room for it plus a
# reference-price change, and still sits far below the smallest real split (2:1
# is a 50% step).
BAND = 0.20

# A ratio is named only when a tidy fraction lands within this much of it, and
# only when the fraction is one a company would actually announce: a split is
# 2:1 or 3:2 or 10:1, never 28:15. Without the caps, `limit_denominator` returns
# the CLOSEST fraction rather than a plausible one, and 1.8697 comes back as
# "28:15" — a decision nobody took, printed as fact.
LABEL_TOLERANCE = 0.005
LABEL_MAX_DENOMINATOR = 5
LABEL_MAX_NUMERATOR = 50

# Families with a price band and a share count: these are the ones that split.
# Gold, crypto and FX have no band, an index is a computed level, and a future
# is a contract — a 20% session in any of those is a 20% session.
ADJUSTABLE_CLASSES = {"equity", "fund"}


@dataclass(frozen=True)
class Event:
    """One redenomination, as read off the prices."""

    open_time: int          # the first session on the new scale, epoch ms
    ratio: float            # old price / new price: 2.0 is a two-for-one split
    previous_close: float
    close: float
    kind: str               # "split" (more shares) or "reverse_split" (fewer)

    @property
    def label(self) -> str | None:
        return ratio_label(self.ratio)

    def as_dict(self) -> dict:
        return {
            "open_time": self.open_time,
            "ratio": self.ratio,
            "previous_close": self.previous_close,
            "close": self.close,
            "kind": self.kind,
            "label": self.label,
        }


def applies_to(symbol: str) -> bool:
    """Whether this symbol is the kind of thing that can split."""
    from backend.data import market_vn

    name = (symbol or "").upper()
    if name.startswith("VN:"):
        name = name[3:]
    return market_vn.classify(name) in ADJUSTABLE_CLASSES


def ratio_label(ratio: float) -> str | None:
    """"2:1" for a ratio that is one, None for a ratio that is not.

    Naming is for the reader only — the adjustment uses the measured ratio, so
    an unnamed event is corrected exactly like a named one. Inventing "44:1"
    for a step of 44.33 would be claiming knowledge of a decision nobody here
    has seen.
    """
    if not ratio or ratio <= 0:
        return None
    fraction = Fraction(ratio).limit_denominator(LABEL_MAX_DENOMINATOR)
    if fraction.denominator == 0 or fraction.numerator > LABEL_MAX_NUMERATOR:
        return None
    if abs(float(fraction) - ratio) > LABEL_TOLERANCE * ratio:
        return None
    return f"{fraction.numerator}:{fraction.denominator}"


def detect(frame: pd.DataFrame, band: float = BAND) -> list[Event]:
    """Every session whose step past the band makes it a redenomination."""
    if frame is None or len(frame) < 2 or "close" not in frame:
        return []

    closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype="float64")
    times = frame["open_time"].to_numpy()
    events: list[Event] = []
    for i in range(1, len(closes)):
        before, after = closes[i - 1], closes[i]
        if not (before > 0 and after > 0):
            continue
        change = after / before - 1.0
        if abs(change) < band:
            continue
        events.append(Event(
            open_time=int(times[i]),
            ratio=float(before / after),
            previous_close=float(before),
            close=float(after),
            kind="split" if change < 0 else "reverse_split",
        ))
    return events


def adjust(frame: pd.DataFrame, events: list[Event] | None = None):
    """Back-adjust a frame onto today's scale. Returns (frame, events).

    Back-adjusted rather than forward-adjusted: the newest bars are left exactly
    as they traded, and the history is restated in today's units. Anything the
    reader checks against a broker screen — the last price, an open position, a
    level they set — then still matches, and only the past moves.
    """
    events = detect(frame) if events is None else events
    if frame is None or not len(frame) or not events:
        return frame, events or []

    out = frame.copy()
    times = out["open_time"].to_numpy()
    # A bar is divided by every ratio that came after it; prices before a
    # two-for-one split are halved onto the post-split scale.
    factor = pd.Series(1.0, index=out.index)
    for event in events:
        factor = factor * pd.Series(
            [1.0 / event.ratio if t < event.open_time else 1.0 for t in times],
            index=out.index,
        )

    for column in ("open", "high", "low", "close"):
        if column in out:
            out[column] = pd.to_numeric(out[column], errors="coerce") * factor
    if "volume" in out:
        # The other way round: half the price, twice the shares.
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce") / factor

    return out, events
