"""EGARCH Student-t risk features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from arch import arch_model


@dataclass
class EGARCHResult:
    features: pd.DataFrame
    diagnostics: dict[str, object]


def fit_egarch_features(returns: pd.Series, train_idx: np.ndarray) -> EGARCHResult:
    """Fit EGARCH Student-t on train and filter volatility causally for all rows.

    If EGARCH fails to converge, the fallback is EWMA volatility and is recorded.
    """
    ret = returns.fillna(0.0).astype(float)
    warnings: list[str] = []
    params: dict[str, float] = {}
    try:
        am = arch_model(ret.iloc[train_idx] * 100, vol="EGARCH", p=1, o=1, q=1, dist="StudentsT", mean="Constant", rescale=False)
        res = am.fit(disp="off", show_warning=False)
        params = {k: float(v) for k, v in res.params.items()}
        omega = params.get("omega", -0.1)
        alpha = params.get("alpha[1]", 0.1)
        gamma = params.get("gamma[1]", 0.0)
        beta = min(max(params.get("beta[1]", 0.9), 0.0), 0.995)
        log_var = np.empty(len(ret))
        std_resid = np.empty(len(ret))
        init_var = float(np.nanvar(ret.iloc[train_idx] * 100) + 1e-6)
        log_var[0] = np.log(init_var)
        std_resid[0] = 0.0
        e_abs = np.sqrt(2 / np.pi)
        mu = params.get("mu", 0.0)
        for i in range(1, len(ret)):
            z_prev = ((ret.iloc[i - 1] * 100) - mu) / np.sqrt(np.exp(log_var[i - 1]))
            std_resid[i - 1] = z_prev
            log_var[i] = omega + beta * log_var[i - 1] + alpha * (abs(z_prev) - e_abs) + gamma * z_prev
            log_var[i] = float(np.clip(log_var[i], -20, 20))
        std_resid[-1] = ((ret.iloc[-1] * 100) - mu) / np.sqrt(np.exp(log_var[-1]))
        sigma = np.sqrt(np.exp(log_var)) / 100.0
        converged = bool(getattr(res, "convergence_flag", 1) == 0)
        if not converged:
            warnings.append("EGARCH optimizer did not report clean convergence")
    except Exception as exc:  # pragma: no cover - optimizer dependent
        warnings.append(f"EGARCH failed; fallback EWMA volatility used: {exc}")
        sigma = (
            ret.ewm(span=40, adjust=False, min_periods=5)
            .std()
            .fillna(ret.expanding(min_periods=2).std())
            .fillna(1e-4)
            .clip(lower=1e-6)
            .to_numpy()
        )
        log_var = np.log(np.maximum(sigma**2, 1e-12))
        std_resid = (ret / np.maximum(sigma, 1e-8)).clip(-20, 20).to_numpy()
        converged = False
    f = pd.DataFrame(index=returns.index)
    f["egarch_sigma"] = sigma
    f["egarch_log_variance"] = log_var
    f["egarch_standardized_residual"] = std_resid
    f["egarch_negative_shock"] = np.minimum(std_resid, 0)
    f["egarch_volatility_percentile"] = pd.Series(sigma, index=returns.index).rolling(252, min_periods=40).rank(pct=True)
    f["egarch_volatility_change"] = pd.Series(sigma, index=returns.index).pct_change()
    f["egarch_tail_risk_score"] = f["egarch_sigma"] * (1 + f["egarch_negative_shock"].abs())
    return EGARCHResult(
        features=f.replace([np.inf, -np.inf], np.nan),
        diagnostics={
            "converged": converged,
            "params": params,
            "warnings": warnings,
            "dist": "StudentsT",
            "nu": float(params.get("nu", 8.0)),
        },
    )
