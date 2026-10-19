"""Prespecified F08 quotas. No imports from any other experiment."""
import numpy as np

CONDITIONS = ('dose25','dose4375','dose625','dose8125','i_then_j','j_then_i','alternate4k','mixture')
PAIR_INDICES = {'A': (0,1), 'B': (3,0), 'C': (1,3)}


def quotas(candidate, block_index, suite):
    i,j = PAIR_INDICES[suite]
    if candidate.startswith('dose'):
        focus,other = {'dose25':(4,4),'dose4375':(7,3),'dose625':(10,2),'dose8125':(13,1)}[candidate]
        result = [other]*4
        result[i] = focus
    else:
        result = [1]*4
        if candidate == 'mixture':
            result[i] = result[j] = 3
        else:
            if candidate == 'i_then_j':task = i if block_index < 5 else j
            elif candidate == 'j_then_i':task = j if block_index < 5 else i
            elif candidate == 'alternate4k':task = i if block_index % 2 == 0 else j
            else:raise ValueError(candidate)
            result[task] = 5
    return tuple(result)


def full_plan(candidate, seed, suite):
    rng = np.random.default_rng(seed)
    blocks = 5 if candidate.startswith('dose') else 10
    return [int(t) for b in range(blocks) for t in rng.permutation(np.repeat(np.arange(4), quotas(candidate,b,suite)))]
