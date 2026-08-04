from __future__ import annotations
import csv, re
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = {"date", "close"}

def _number(parts: list[str]) -> float:
    clean=[float(x.strip().replace(" ","")) for x in parts]
    return sum(value*(1000**(len(clean)-i-1)) for i,value in enumerate(clean))

def _parse_broken_csv(path: Path) -> pd.DataFrame:
    """Recover the common unquoted-thousands CSV export without touching source."""
    rows = []
    previous_close = None
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        for line_no, raw in enumerate(reader, 2):
            cells = [x.strip() for x in raw]
            while cells and cells[-1] == "": cells.pop()
            if len(cells) < 6: continue
            date, tokens = cells[0], cells[1:]
            candidates = []
            # OHLC are either one token or a thousands-prefix plus decimal token.
            for a in (1, 2):
              for b in (1, 2):
               for c in (1, 2):
                for d in (1, 2):
                 cuts = [a,b,c,d]; pos=0
                 try:
                    vals=[]
                    for n in cuts: vals.append(_number(tokens[pos:pos+n])); pos += n
                    vol = _number(tokens[pos:])
                    o,h,l,cl = vals
                    if min(vals)>0 and vol >= 0:
                        # Keep malformed-but-parseable OHLC rows for the quality report.
                        violations = int(h < max(o,cl)-1e-9) + int(l > min(o,cl)+1e-9)
                        continuity = 0 if previous_close is None else abs(np.log(cl/previous_close))
                        coherence = (abs(o-cl)+abs(h-cl)+abs(l-cl))/max(cl,1)
                        score = 100*violations + 50*coherence + 5*continuity + (0 if pos < len(tokens) else 10)
                        candidates.append((score, [date,o,h,l,cl,vol]))
                 except (ValueError, IndexError): pass
            if candidates:
                chosen=min(candidates, key=lambda x:x[0])[1]; rows.append(chosen); previous_close=chosen[4]
            else: raise ValueError(f"Cannot reconstruct OHLCV at line {line_no}")
    return pd.DataFrame(rows, columns=["Date","Open","High","Low","Close","Volume"])

def load_market_data(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as probe:
            if len(next(csv.reader([probe.readline()]))) > 6:
                raise ValueError("Unquoted thousands export")
        frame = pd.read_csv(path)
        frame = frame.loc[:, ~frame.columns.astype(str).str.startswith("Unnamed")]
        frame.columns = [str(c).strip().lower() for c in frame.columns]
        if not REQUIRED <= set(frame.columns) or frame["close"].isna().mean() > .2:
            raise ValueError("Malformed ordinary CSV")
    except Exception:
        frame = _parse_broken_csv(path)
        frame.columns = [c.lower() for c in frame.columns]
    frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
    for col in frame.columns.difference(["date"]):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    frame = frame.drop_duplicates("date", keep="last").reset_index(drop=True)
    if (frame.close <= 0).any(): raise ValueError("Close must be positive")
    return frame

def discover_data(root: str | Path = ".") -> Path:
    root = Path(root)
    preferred = [root/"data/raw/VNINDEX_Daily.csv", root/"VNINDEX_Daily.csv", root/"data.csv"]
    candidates = [p for p in preferred if p.exists()]
    candidates += [p for p in root.rglob("*VNINDEX*.csv") if p not in candidates]
    if not candidates: raise FileNotFoundError("Place VNINDEX_Daily.csv under data/raw/")
    return max(candidates, key=lambda p: load_market_data(p).date.max())
