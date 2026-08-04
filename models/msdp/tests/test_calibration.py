import numpy as np
from msdp.calibration import StaticCQRCalibrator,RollingCQRCalibrator,causal_conformal_comparison,conformity_scores

def test_conformity_score_cases_and_interval_expansion():
    lo=np.array([[-1.],[-1.],[-1.]]); hi=np.array([[1.],[1.],[1.]]); y=np.array([[0.],[-2.],[3.]])
    assert np.array_equal(conformity_scores(lo,hi,y).ravel(),[0,1,2])
    c=StaticCQRCalibrator().fit(lo,hi,y); a,b=c.transform_all_horizons(lo,hi)
    assert (c.qhat>=0).all() and (a<=lo).all() and (b>=hi).all()

def test_rolling_does_not_use_unmatured_future_residual():
    r=RollingCQRCalibrator(window=20,horizons=(5,20,60)).seed(np.zeros((3,3)),np.ones((3,3)),np.full((3,3),.5)); before=len(r.history)
    r.update(np.zeros(3),np.ones(3),np.array([2.,2.,2.]),forecast_time=10); r.predict(np.zeros(3),np.ones(3),current_time=14); assert len(r.history)==before
    r.predict(np.zeros(3),np.ones(3),current_time=15); assert len(r.history)==before+1

def test_static_uses_distinct_qhat_and_rejects_broadcasting():
    import pytest
    c=StaticCQRCalibrator(.1); c.qhat=np.array([1.,5.,10.]); lo=np.zeros((1,3)); hi=np.ones((1,3)); a,b=c.transform_all_horizons(lo,hi); assert np.array_equal(a,[[-1,-5,-10]]) and np.array_equal(b,[[2,6,11]])
    assert np.all(a<=lo) and np.all(b>=hi) and np.all(c.qhat>=0)
    with pytest.raises(ValueError): c.transform_all_horizons(np.array([0.]),np.array([1.]))
    with pytest.raises(IndexError): c.transform_horizon(np.array([0.]),np.array([1.]),3)
    x,y=c.transform_horizon(np.array([0.]),np.array([1.]),1); assert x[0]==-5 and y[0]==6

def test_causal_comparison_does_not_use_future_residual():
    cal=np.zeros((20,3)); ycal=np.zeros((20,3)); lo=np.zeros((8,3)); hi=np.ones((8,3)); y=np.zeros((8,3))
    base=causal_conformal_comparison(cal,cal,ycal,lo,hi,y); y_future=y.copy(); y_future[-1]=1000
    changed=causal_conformal_comparison(cal,cal,ycal,lo,hi,y_future)
    assert np.array_equal(base["rolling"][0][:-1],changed["rolling"][0][:-1])
    assert np.array_equal(base["adaptive"][1][:-1],changed["adaptive"][1][:-1])
