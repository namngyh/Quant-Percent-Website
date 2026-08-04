import numpy as np
import pytest

from msdp.models import (
    BaselineOutput, HistoricalFrequencyDirectionBaseline, HistoricalMeanBaseline,
    LogisticDirectionBaseline, RidgeDirectBaseline,
    UnconditionalEmpiricalDistributionBaseline, ZeroPointForecastBaseline,
)


def sample(seed=7, n=80, h=3, p=5):
    rng=np.random.default_rng(seed); x=rng.normal(size=(n,p)); r=x[:,:3]*.2+rng.normal(size=(n,h)); d=(r>0).astype(float)
    m=-np.abs(rng.normal(size=(n,h))); v=np.abs(rng.normal(10,2,size=(n,h)))
    return x,r,d,m,v


def test_baseline_output_schema_and_supported_targets():
    x,r,d,m,v=sample(); qr=(.05,.5,.95); qm=(.1,.5,.9)
    outputs=[ZeroPointForecastBaseline().fit(r).predict(4),
             UnconditionalEmpiricalDistributionBaseline().fit(r,m,v,qr,qm).predict(4),
             HistoricalFrequencyDirectionBaseline().fit(d).predict(4),
             HistoricalMeanBaseline().fit(r,qr).predict(4),
             RidgeDirectBaseline().fit(x,r,qr).predict(x[-4:]),
             LogisticDirectionBaseline().fit(x,d).predict(x[-4:])]
    assert all(isinstance(o,BaselineOutput) and o.baseline_name for o in outputs)
    assert outputs[0].return_point.shape==(4,3) and outputs[0].return_quantiles is None and outputs[0].direction_probability is None
    assert outputs[1].return_quantiles.shape==(4,3,3) and outputs[1].mdd_quantiles.shape==(4,3,3)
    assert outputs[2].direction_probability.shape==(4,3) and outputs[2].return_point is None
    assert outputs[5].direction_probability.shape==(4,3) and outputs[5].return_quantiles is None


def test_historical_mean_is_not_zero_and_residuals_are_out_of_sample():
    _,r,_,_,_=sample(); r=r+2
    out=HistoricalMeanBaseline().fit(r,(.1,.5,.9)).predict(3)
    assert not np.allclose(out.return_point,0)
    assert out.metadata["residual_source"]=="internal chronological validation"


def test_ridge_uses_validation_residual_and_logistic_never_sees_predict_rows():
    x,r,d,_,_=sample(); ridge=RidgeDirectBaseline().fit(x[:60],r[:60],(.1,.5,.9)); out=ridge.predict(x[60:])
    assert out.metadata["residual_rows"]<out.metadata["fit_rows"]
    assert out.metadata["residual_source"]=="internal chronological validation"
    logistic=LogisticDirectionBaseline().fit(x[:60],d[:60]); pred=logistic.predict(x[60:])
    assert pred.metadata["fit_rows"]==60 and pred.direction_probability.shape==(20,3)


def test_baseline_validation_rejects_invalid_data():
    with pytest.raises(ValueError): ZeroPointForecastBaseline().predict(2)
    with pytest.raises(ValueError): HistoricalFrequencyDirectionBaseline().fit([[0,2],[1,0]])
