"""Bollinger Band dùng Normal Inverse Gaussian (NIG)."""

import numpy as np
import pandas as pd

from scipy.stats import norminvgauss


STRATEGY = {
    "name": "Bollinger NIG Mean Reversion",
    "side": "both",
    "params": {
        "length": {
            "type": "int",
            "default": 120,
            "min": 30,
            "max": 1000,
        },

        "tail_prob": {
            "type": "float",
            "default": 0.02275,
            "min": 0.001,
            "max": 0.20,
        },

        "refit_every": {
            "type": "int",
            "default": 5,
            "min": 1,
            "max": 100,
        },
    },
}


def _fit_nig_quantiles(z, alpha):
    """
    Fit Normal Inverse Gaussian lên standardized deviations.

    SciPy trả về:
        a, b, loc, scale
    """

    z = np.asarray(z, dtype=float)
    z = z[np.isfinite(z)]

    if len(z) < 20:
        return np.nan, np.nan

    try:
        a, b, loc, scale = norminvgauss.fit(z)

        # Kiểm tra tham số hợp lệ
        if (
            not np.isfinite(a)
            or not np.isfinite(b)
            or not np.isfinite(loc)
            or not np.isfinite(scale)
            or a <= 0
            or abs(b) >= a
            or scale <= 0
        ):
            raise ValueError("Invalid NIG parameters")

        q_lower = norminvgauss.ppf(
            alpha,
            a,
            b,
            loc=loc,
            scale=scale,
        )

        q_upper = norminvgauss.ppf(
            1.0 - alpha,
            a,
            b,
            loc=loc,
            scale=scale,
        )

        if not (
            np.isfinite(q_lower)
            and np.isfinite(q_upper)
        ):
            raise ValueError("Invalid NIG quantiles")

        return float(q_lower), float(q_upper)

    except Exception:

        # Fallback về empirical quantile
        return (
            float(np.quantile(z, alpha)),
            float(np.quantile(z, 1.0 - alpha)),
        )


def _bands(df, length, alpha, refit_every):

    close = df["close"].astype(float)

    middle = close.rolling(length).mean()
    scale = close.rolling(length).std(ddof=1)

    lower = pd.Series(
        np.nan,
        index=df.index,
        dtype=float,
    )

    upper = pd.Series(
        np.nan,
        index=df.index,
        dtype=float,
    )

    q_lower = np.nan
    q_upper = np.nan

    for i in range(length - 1, len(df)):

        window = close.iloc[
            i - length + 1:i + 1
        ].to_numpy()

        mu = float(np.mean(window))
        sigma = float(np.std(window, ddof=1))

        if (
            not np.isfinite(sigma)
            or sigma <= 0
        ):
            continue

        # Chuẩn hóa deviation
        z = (window - mu) / sigma

        # NIG MLE tương đối nặng,
        # nên không fit lại mỗi candle
        if (
            (i - (length - 1)) % refit_every == 0
            or not np.isfinite(q_lower)
            or not np.isfinite(q_upper)
        ):

            q_lower, q_upper = _fit_nig_quantiles(
                z,
                alpha,
            )

        lower.iloc[i] = (
            mu + sigma * q_lower
        )

        upper.iloc[i] = (
            mu + sigma * q_upper
        )

    return middle, lower, upper


def signals(df, params):
    """
    Mean-reversion:

    LONG:
        close <= NIG lower band
        exit khi close >= middle

    SHORT:
        close >= NIG upper band
        exit khi close <= middle

    Không look-ahead.
    """

    length = int(params["length"])
    alpha = float(params["tail_prob"])
    refit_every = int(params["refit_every"])

    close = df["close"].astype(float)

    middle, lower, upper = _bands(
        df=df,
        length=length,
        alpha=alpha,
        refit_every=refit_every,
    )

    position = np.zeros(
        len(df),
        dtype=int,
    )

    state = 0

    for i in range(length - 1, len(df)):

        c = close.iloc[i]
        m = middle.iloc[i]
        lo = lower.iloc[i]
        hi = upper.iloc[i]

        if not (
            np.isfinite(c)
            and np.isfinite(m)
            and np.isfinite(lo)
            and np.isfinite(hi)
        ):
            position[i] = state
            continue

        # FLAT
        if state == 0:

            if c <= lo:
                state = 1

            elif c >= hi:
                state = -1

        # LONG
        elif state == 1:

            if c >= m:
                state = 0

        # SHORT
        elif state == -1:

            if c <= m:
                state = 0

        position[i] = state

    return pd.Series(
        position,
        index=df.index,
    )