"""Các baseline ngoài mẫu dùng chung một schema dự báo rõ ràng."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
import warnings

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss, mean_squared_error
from sklearn.preprocessing import StandardScaler


Array = np.ndarray


@dataclass(frozen=True)
class BaselineOutput:
    """Schema dự báo; trường không được mô hình cung cấp phải giữ ``None``."""

    return_point: Array | None = None
    return_quantiles: Array | None = None
    direction_probability: Array | None = None
    mdd_quantiles: Array | None = None
    volatility: Array | None = None
    baseline_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _matrix(value: Any, name: str, *, binary: bool = False) -> Array:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 1 or not np.isfinite(arr).all():
        raise ValueError(f"{name} phải là ma trận hữu hạn [N, H] với N >= 2")
    if binary and not np.isin(arr, (0.0, 1.0)).all():
        raise ValueError(f"{name} chỉ được chứa 0/1")
    return arr


def _features(value: Any, name: str = "x") -> Array:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 1 or not np.isfinite(arr).all():
        raise ValueError(f"{name} phải là ma trận đặc trưng hữu hạn [N, P]")
    return arr


def _quantiles(value: Sequence[float], name: str) -> Array:
    q = np.asarray(value, dtype=float)
    if q.ndim != 1 or len(q) < 1 or np.any(np.diff(q) <= 0) or np.any((q <= 0) | (q >= 1)):
        raise ValueError(f"{name} phải tăng nghiêm ngặt và nằm trong (0, 1)")
    return q


def _count(n: int) -> int:
    n = int(n)
    if n < 1:
        raise ValueError("n phải >= 1")
    return n


class ZeroPointForecastBaseline:
    """Dự báo điểm lợi suất bằng 0, không tạo phân vị hoặc xác suất giả."""

    name = "zero_point"

    def fit(self, returns: Any | None = None) -> "ZeroPointForecastBaseline":
        if returns is not None:
            self.n_horizons_ = _matrix(returns, "returns").shape[1]
        return self

    def predict(self, n: int, n_horizons: int | None = None) -> BaselineOutput:
        h = int(n_horizons or getattr(self, "n_horizons_", 0))
        if h < 1:
            raise ValueError("n_horizons phải được cung cấp hoặc suy ra từ fit")
        return BaselineOutput(return_point=np.zeros((_count(n), h)), baseline_name=self.name,
                              metadata={"fit_data": "không cần fit"})


class UnconditionalEmpiricalDistributionBaseline:
    """Phân phối thực nghiệm theo horizon, fit duy nhất trên training target."""

    name = "unconditional_empirical_distribution"

    def __init__(self, volatility_statistic: str = "median") -> None:
        if volatility_statistic not in {"median", "mean"}:
            raise ValueError("volatility_statistic phải là median hoặc mean")
        self.volatility_statistic = volatility_statistic

    def fit(self, returns: Any, mdd: Any, volatility: Any, return_quantiles: Sequence[float],
            mdd_quantiles: Sequence[float]) -> "UnconditionalEmpiricalDistributionBaseline":
        r, d, v = _matrix(returns, "returns"), _matrix(mdd, "mdd"), _matrix(volatility, "volatility")
        if r.shape != d.shape or r.shape != v.shape:
            raise ValueError("returns, mdd và volatility phải cùng shape")
        qr, qm = _quantiles(return_quantiles, "return_quantiles"), _quantiles(mdd_quantiles, "mdd_quantiles")
        self.return_q_ = np.quantile(r, qr, axis=0).T
        self.mdd_q_ = np.quantile(d, qm, axis=0).T
        self.volatility_ = (np.median(v, axis=0) if self.volatility_statistic == "median" else np.mean(v, axis=0))
        self.metadata_ = {"fit_rows": len(r), "fit_data": "outer training target", "residual_source": "không áp dụng"}
        return self

    def predict(self, n: int) -> BaselineOutput:
        if not hasattr(self, "return_q_"):
            raise RuntimeError("Baseline chưa được fit")
        n = _count(n)
        return BaselineOutput(return_quantiles=np.tile(self.return_q_[None], (n, 1, 1)),
                              mdd_quantiles=np.tile(self.mdd_q_[None], (n, 1, 1)),
                              volatility=np.tile(self.volatility_[None], (n, 1)), baseline_name=self.name,
                              metadata=self.metadata_)


class HistoricalFrequencyDirectionBaseline:
    """Xác suất tăng bằng tần suất tăng trên training cho từng horizon."""

    name = "historical_frequency_direction"

    def fit(self, direction: Any) -> "HistoricalFrequencyDirectionBaseline":
        y = _matrix(direction, "direction", binary=True)
        self.frequency_ = np.mean(y, axis=0)
        self.metadata_ = {"fit_rows": len(y), "fit_data": "outer training direction"}
        return self

    def predict(self, n: int) -> BaselineOutput:
        if not hasattr(self, "frequency_"):
            raise RuntimeError("Baseline chưa được fit")
        return BaselineOutput(direction_probability=np.tile(self.frequency_[None], (_count(n), 1)),
                              baseline_name=self.name, metadata=self.metadata_)


class HistoricalMeanBaseline:
    """Trung bình lịch sử và phân vị residual từ validation theo thời gian."""

    name = "historical_mean"

    def fit(self, returns: Any, quantiles: Sequence[float], validation_fraction: float = 0.2) -> "HistoricalMeanBaseline":
        y, q = _matrix(returns, "returns"), _quantiles(quantiles, "quantiles")
        cut = int(np.floor(len(y) * (1 - validation_fraction)))
        if cut < 2 or len(y) - cut < 2:
            raise ValueError("Không đủ dữ liệu cho internal chronological validation")
        inner_mean = np.mean(y[:cut], axis=0)
        residual = y[cut:] - inner_mean
        self.mean_ = np.mean(y, axis=0)
        self.residual_q_ = np.quantile(residual, q, axis=0).T
        self.metadata_ = {"fit_rows": len(y), "inner_train_rows": cut, "residual_rows": len(residual),
                          "residual_source": "internal chronological validation"}
        return self

    def predict(self, n: int) -> BaselineOutput:
        if not hasattr(self, "mean_"):
            raise RuntimeError("Baseline chưa được fit")
        n = _count(n); point = np.tile(self.mean_[None], (n, 1))
        quantiles = point[:, :, None] + self.residual_q_[None]
        return BaselineOutput(return_point=point, return_quantiles=quantiles, baseline_name=self.name,
                              metadata=self.metadata_)


class RidgeDirectBaseline:
    """Ridge trực tiếp; alpha và residual quantile dùng validation tuần tự nội bộ."""

    name = "ridge_direct"

    def __init__(self, alphas: Sequence[float] = (0.1, 1.0, 10.0), validation_fraction: float = 0.2) -> None:
        self.alphas = tuple(float(a) for a in alphas)
        self.validation_fraction = float(validation_fraction)
        if not self.alphas or any(a <= 0 for a in self.alphas):
            raise ValueError("alphas phải dương")

    def fit(self, x: Any, y: Any, quantiles: Sequence[float]) -> "RidgeDirectBaseline":
        x, y, q = _features(x), _matrix(y, "y"), _quantiles(quantiles, "quantiles")
        if len(x) != len(y): raise ValueError("x và y phải cùng số dòng")
        cut = int(np.floor(len(x) * (1 - self.validation_fraction)))
        if cut < 2 or len(x) - cut < 2: raise ValueError("Không đủ dữ liệu cho inner validation")
        scaler = StandardScaler().fit(x[:cut]); xi, xv = scaler.transform(x[:cut]), scaler.transform(x[cut:])
        self.best_alphas_ = [] ; residual_columns = []
        for j in range(y.shape[1]):
            losses = []
            for alpha in self.alphas:
                pred = Ridge(alpha=alpha).fit(xi, y[:cut, j]).predict(xv)
                losses.append(mean_squared_error(y[cut:, j], pred))
            alpha = self.alphas[int(np.argmin(losses))]; self.best_alphas_.append(alpha)
            residual_columns.append(y[cut:, j] - Ridge(alpha=alpha).fit(xi, y[:cut, j]).predict(xv))
        residual = np.stack(residual_columns, axis=1)
        self.residual_q_ = np.quantile(residual, q, axis=0).T
        self.scaler_ = StandardScaler().fit(x); xf = self.scaler_.transform(x)
        self.models_ = [Ridge(alpha=a).fit(xf, y[:, j]) for j, a in enumerate(self.best_alphas_)]
        self.metadata_ = {"fit_rows": len(x), "inner_train_rows": cut, "residual_rows": len(residual),
                          "residual_source": "internal chronological validation", "selected_alpha": self.best_alphas_}
        return self

    def predict(self, x: Any) -> BaselineOutput:
        if not hasattr(self, "models_"): raise RuntimeError("Baseline chưa được fit")
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.scaler_.n_features_in_ or not np.isfinite(x).all():
            raise ValueError("x dự báo không khớp feature training")
        z = self.scaler_.transform(x); point = np.stack([m.predict(z) for m in self.models_], axis=1)
        return BaselineOutput(return_point=point, return_quantiles=point[:, :, None] + self.residual_q_[None],
                              baseline_name=self.name, metadata=self.metadata_)


class LogisticDirectionBaseline:
    """Logistic theo horizon; C chọn bằng log-loss trên validation tuần tự nội bộ."""

    name = "logistic_direction"

    def __init__(self, c_values: Sequence[float] = (0.1, 1.0, 10.0), class_weight: str | dict | None = None,
                 validation_fraction: float = 0.2) -> None:
        self.c_values = tuple(float(c) for c in c_values); self.class_weight = class_weight
        self.validation_fraction = float(validation_fraction)
        if not self.c_values or any(c <= 0 for c in self.c_values): raise ValueError("c_values phải dương")

    def fit(self, x: Any, y: Any) -> "LogisticDirectionBaseline":
        x, y = _features(x), _matrix(y, "y", binary=True)
        if len(x) != len(y): raise ValueError("x và y phải cùng số dòng")
        cut = int(np.floor(len(x) * (1 - self.validation_fraction)))
        if cut < 2 or len(x) - cut < 2: raise ValueError("Không đủ dữ liệu cho inner validation")
        scaler = StandardScaler().fit(x[:cut]); xi, xv = scaler.transform(x[:cut]), scaler.transform(x[cut:])
        self.best_c_ = []
        for j in range(y.shape[1]):
            if len(np.unique(y[:cut, j])) < 2: raise ValueError(f"Horizon {j} chỉ có một lớp trong inner train")
            losses=[]
            for c in self.c_values:
                p=LogisticRegression(C=c,class_weight=self.class_weight,max_iter=1000).fit(xi,y[:cut,j].astype(int)).predict_proba(xv)[:,1]
                losses.append(log_loss(y[cut:,j],np.clip(p,1e-8,1-1e-8),labels=[0,1]))
            self.best_c_.append(self.c_values[int(np.argmin(losses))])
        self.scaler_=StandardScaler().fit(x); xf=self.scaler_.transform(x)
        self.models_=[LogisticRegression(C=c,class_weight=self.class_weight,max_iter=1000).fit(xf,y[:,j].astype(int)) for j,c in enumerate(self.best_c_)]
        self.metadata_={"fit_rows":len(x),"inner_train_rows":cut,"selection_data":"internal chronological validation","selected_c":self.best_c_}
        return self

    def predict(self, x: Any) -> BaselineOutput:
        if not hasattr(self,"models_"): raise RuntimeError("Baseline chưa được fit")
        x=np.asarray(x,dtype=float)
        if x.ndim!=2 or x.shape[1]!=self.scaler_.n_features_in_ or not np.isfinite(x).all(): raise ValueError("x dự báo không khớp feature training")
        z=self.scaler_.transform(x); p=np.stack([m.predict_proba(z)[:,1] for m in self.models_],axis=1)
        return BaselineOutput(direction_probability=p,baseline_name=self.name,metadata=self.metadata_)


class ZeroReturnBaseline(UnconditionalEmpiricalDistributionBaseline):
    """Alias cũ đã deprecated; pipeline mới không được sử dụng."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn("ZeroReturnBaseline đã deprecated; dùng baseline đúng theo từng metric", DeprecationWarning, stacklevel=2)
        super().__init__(*args, **kwargs)
