import numpy as np

EXPERTS=["short","medium","long","range_vol"]
def confidence_score(width_percentile,coverage_error,disagreement,seed_dispersion=0,drift=0):
    penalty=.30*width_percentile+.25*min(1,coverage_error/.1)+.20*disagreement+.10*seed_dispersion+.15*drift; score=int(round(100*(1-min(1,penalty)))); return score,"Cao" if score>=70 else "Trung bình" if score>=40 else "Thấp"

def percentile_rank(value,history):
    history=np.asarray(history,dtype=float); history=history[np.isfinite(history)]
    if not np.isfinite(value) or not len(history): return None
    return float((np.sum(history<value)+.5*np.sum(history==value))/len(history))

def latest_seed_dispersions(latest_seed_predictions):
    if not latest_seed_predictions: raise ValueError("latest_seed_predictions is empty")
    out=[]
    h=latest_seed_predictions[0]["return_quantiles"].shape[1]
    for j in range(h):
        out.append({
            "return":float(np.std([p["return_quantiles"][0,j,2] for p in latest_seed_predictions])),
            "direction":float(np.std([p["direction_prob"][0,j] for p in latest_seed_predictions])),
            "mdd":float(np.std([p["mdd_quantiles"][0,j,1] for p in latest_seed_predictions])),
            "volatility":float(np.std([p["volatility"][0,j] for p in latest_seed_predictions])),
        })
    return out

def artifact_confidence(components,sources,weights=None):
    weights=weights or {"interval":.30,"coverage":.20,"disagreement":.20,"seed":.15,"drift":.15}
    used={k:float(np.clip(v,0,1)) for k,v in components.items() if v is not None and np.isfinite(v) and k in weights}; missing=[k for k in weights if k not in used]
    if not used: return {"score":None,"label":"Không khả dụng","components":components,"component_sources":sources,"missing_components":missing,"used_components":[]}
    denom=sum(weights[k] for k in used); uncertainty=sum(weights[k]*v for k,v in used.items())/denom; score=float(100*(1-uncertainty)); label="Cao" if score>=70 else "Trung bình" if score>=40 else "Thấp"
    return {"score":score,"label":label,"components":components,"component_sources":sources,"missing_components":missing,"used_components":list(used)}
def interpret(horizons,p_up,weights,width_percentile=None,mdd_q10=None):
    notes=[]
    names={"short":"ngắn hạn","medium":"trung hạn","long":"dài hạn","range_vol":"biên độ–biến động"}
    if p_up[0]<.45 and p_up[-1]>.60: notes.append("Tín hiệu ngắn hạn nghiêng giảm trong khi triển vọng dài hơn nghiêng tăng.")
    for j,h in enumerate(horizons): notes.append(f"Dự báo {h} phiên chịu ảnh hưởng lớn nhất từ chuyên gia {names[EXPERTS[int(np.argmax(weights[j]))]]}.")
    if width_percentile is not None and width_percentile>.8: notes.append("Bất định dự báo cao hơn phần lớn lịch sử.")
    if mdd_q10 is not None and np.min(mdd_q10)<-10: notes.append("Kịch bản bất lợi chứa mức sụt giảm đáng kể.")
    return notes
