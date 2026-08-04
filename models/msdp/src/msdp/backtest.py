import numpy as np

def diagnostic_long_cash(returns,p_up,q05,width,confidence,cost_bps=10):
    exposure=((p_up>.55)&(q05>-5)&(width<np.nanmedian(width))&(confidence>=40)).astype(float); turnover=np.abs(np.diff(exposure,prepend=0)); pnl=exposure*np.asarray(returns)-turnover*cost_bps/10000; return {"exposure":exposure,"returns":pnl,"turnover":turnover}
