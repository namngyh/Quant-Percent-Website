"""Event-level detection metrics.

Day-level recall over-rewards a model that fires late in a long drawdown: a
40-day stress episode contributes 40 easy positives. These metrics collapse
consecutive stress days into episodes and ask the questions an investor asks:

  * how many distinct stress episodes were flagged at all?
  * how many days of warning did the first alert give?
  * how many false alarms per year did that cost?
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.features.targets import stress_events
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def event_detection_metrics(
    labels: pd.Series,
    probabilities: pd.Series,
    threshold: float,
    min_gap_days: int = 20,
    lead_window: int = 40,
) -> dict[str, Any]:
    """Episode-level detection rate, warning lead time and false-alarm rate."""
    labels = labels.dropna()
    probabilities = probabilities.reindex(labels.index)
    valid = probabilities.notna()
    labels, probabilities = labels[valid], probabilities[valid]
    if labels.empty:
        return {"n_events": 0, "note": "no labelled observations"}

    alerts = (probabilities >= threshold).astype(int)
    events = stress_events(labels, min_gap_days=min_gap_days)
    positions = {date: i for i, date in enumerate(labels.index)}

    detected = 0
    lead_times: list[int] = []
    covered = np.zeros(len(labels), dtype=bool)

    for start, end in events:
        start_position = positions[start]
        end_position = positions[end]
        search_start = max(0, start_position - lead_window)
        window = alerts.iloc[search_start : end_position + 1]
        fired = np.where(window.to_numpy() == 1)[0]
        covered[search_start : end_position + 1] = True
        if fired.size:
            first_position = search_start + int(fired[0])
            detected += 1
            lead_times.append(start_position - first_position)

    alert_positions = np.where(alerts.to_numpy() == 1)[0]
    false_alarm_positions = [p for p in alert_positions if not covered[p]]

    # Group consecutive false alarms into episodes so one bad week is not
    # counted as five independent failures.
    false_alarm_events = 0
    previous = -999
    for position in false_alarm_positions:
        if position - previous > min_gap_days:
            false_alarm_events += 1
        previous = position

    n_days = len(labels)
    years = n_days / 252.0

    return {
        "n_events": len(events),
        "n_events_detected": detected,
        "event_detection_rate": float(detected / len(events)) if events else np.nan,
        "n_missed_events": len(events) - detected,
        "mean_warning_lead_days": float(np.mean(lead_times)) if lead_times else np.nan,
        "median_warning_lead_days": float(np.median(lead_times)) if lead_times else np.nan,
        "max_warning_lead_days": float(np.max(lead_times)) if lead_times else np.nan,
        "n_false_alarm_days": len(false_alarm_positions),
        "n_false_alarm_events": false_alarm_events,
        "false_alarm_events_per_year": float(false_alarm_events / years) if years > 0 else np.nan,
        "false_alarm_days_per_year": float(len(false_alarm_positions) / years) if years > 0 else np.nan,
        "alert_rate": float(alerts.mean()),
        "threshold": float(threshold),
        "n_days": n_days,
        "lead_window": lead_window,
    }


def event_table(
    labels: pd.Series,
    probabilities: pd.Series,
    threshold: float,
    min_gap_days: int = 20,
    lead_window: int = 40,
) -> pd.DataFrame:
    """One row per stress episode: dates, detection flag, lead time, peak probability."""
    labels = labels.dropna()
    probabilities = probabilities.reindex(labels.index)
    events = stress_events(labels, min_gap_days=min_gap_days)
    positions = {date: i for i, date in enumerate(labels.index)}
    alerts = (probabilities >= threshold).astype(int)

    rows = []
    for start, end in events:
        start_position, end_position = positions[start], positions[end]
        search_start = max(0, start_position - lead_window)
        window = alerts.iloc[search_start : end_position + 1]
        fired = np.where(window.to_numpy() == 1)[0]
        first_alert = labels.index[search_start + int(fired[0])] if fired.size else pd.NaT
        rows.append(
            {
                "event_start": start,
                "event_end": end,
                "duration_days": end_position - start_position + 1,
                "detected": bool(fired.size),
                "first_alert_date": first_alert,
                "warning_lead_days": (start_position - (search_start + int(fired[0]))) if fired.size else np.nan,
                "max_probability_in_window": float(
                    probabilities.iloc[search_start : end_position + 1].max()
                ),
            }
        )
    return pd.DataFrame(rows)


def regime_breakdown(
    labels: pd.Series,
    probabilities: pd.Series,
    threshold: float,
    regime: pd.Series,
) -> pd.DataFrame:
    """Metrics computed separately per market regime (robustness check)."""
    from dynamicgraph.evaluation.classification import classification_metrics

    frame = pd.DataFrame(
        {"label": labels, "probability": probabilities, "regime": regime}
    ).dropna(subset=["label", "probability", "regime"])

    rows = []
    for name, group in frame.groupby("regime"):
        metrics = classification_metrics(
            group["label"].to_numpy(), group["probability"].to_numpy(), threshold, n_days=len(group)
        )
        metrics["regime"] = name
        rows.append(metrics)
    return pd.DataFrame(rows)
