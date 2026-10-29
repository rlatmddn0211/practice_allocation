"""Independent marginal performance controls; name avoids stdlib profile."""
import numpy as np
PROFILE=['focus', 'cp400', 'p0_0', 'p0_1', 'p0_2', 'p0_3', 'delta_0', 'delta_1', 'delta_2', 'delta_3', 'decline_0', 'decline_1', 'decline_2', 'decline_3']

def role(values,ai):
    return (float(values.mean()),float(values.mean())) if ai==0 else (float(values[ai-1]),float(np.delete(values,ai-1).mean()))

def marginal_features(base,current,ai,cp):
    delta=current-base;bf,bo=role(base,ai);df,do=role(delta,ai)
    row={'focus':int(ai>0),'cp400':int(cp==400000),'initial_focus':bf,'initial_other':bo,'delta_focus':df,'delta_other':do}
    order=sorted(range(4),key=lambda j:(base[j],current[j],j))
    if ai:order=[ai-1]+[j for j in order if j!=ai-1]
    for i,j in enumerate(order):
        row.update({f'p0_{i}':float(base[j]),f'delta_{i}':float(delta[j]),f'decline_{i}':float(max(-delta[j],0))})
    return row

