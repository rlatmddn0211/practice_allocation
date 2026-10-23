"""Reference-only diagnostic probability models. No environment or learner imports."""
import numpy as np

def pava(successes, totals):
    blocks=[]
    for j,(a,b) in enumerate(zip(successes,totals)):
        blocks.append([j,j,float(a),float(b)])
        while len(blocks)>1 and blocks[-2][2]/blocks[-2][3] > blocks[-1][2]/blocks[-1][3]:
            right=blocks.pop(); left=blocks.pop()
            blocks.append([left[0],right[1],left[2]+right[2],left[3]+right[3]])
    values=np.zeros(len(successes))
    for start,end,a,b in blocks: values[start:end+1]=a/b
    return values

def fit(reference, shrinkage=0.25):
    """reference has shape (2 states, 2 completed futures, N common-failure cases)."""
    reference=np.asarray(reference,dtype=np.int64)
    if reference.shape[:2]!=(2,2) or not np.isin(reference,[0,1]).all():
        raise ValueError("Expected binary reference tensor (2,2,N)")
    count=reference.sum(axis=1); common=count.sum(axis=0)
    N=len(common); p0=np.zeros((2,N)); p1=np.zeros((2,N)); bins=[]
    occupied=np.unique(common)
    sizes=np.array([(common==c).sum() for c in occupied])
    probabilities=[]
    for s in range(2):
        successes=np.array([count[s,common==c].sum()+1 for c in occupied])
        probabilities.append(pava(successes,2*sizes+2))
    for j,c in enumerate(occupied):
        mask=common==c
        for s in range(2): p0[s,mask]=probabilities[s][j]
        h=count[0,mask]/2-(count[0,mask]/2).mean()
        bounds=[float(shrinkage)]
        for state,sign in [(0,1),(1,-1)]:
            shift=sign*h; base=probabilities[state][j]
            if (shift>0).any(): bounds.append(float(((1-base)/shift[shift>0]).min()))
            if (shift<0).any(): bounds.append(float((base/(-shift[shift<0])).min()))
        strength=min(bounds)
        p1[0,mask]=p0[0,mask]+strength*h
        p1[1,mask]=p0[1,mask]-strength*h
        bins.append({"common_success_count":int(c),"cases":int(mask.sum()),"state1_M0":float(probabilities[0][j]),"state2_M0":float(probabilities[1][j]),"state1_reference_successes":int(count[0,mask].sum()),"state2_reference_successes":int(count[1,mask].sum()),"strength":strength,"nonzero_direction_cases":int((abs(h)>1e-12).sum())})
    return {"M0":p0,"M1":p1,"difficulty":common,"reference_successes":count,"bins":bins}
