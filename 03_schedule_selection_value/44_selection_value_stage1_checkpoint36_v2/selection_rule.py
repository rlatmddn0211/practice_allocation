"""Frozen stage-2 rule family, pure arithmetic only; no experiment execution."""
from collections import Counter


def score_q(success_counts):
    if set(success_counts)!={'DO','DC','PU','BP'} or any(type(n) is not int or n not in (0,1,2) for n in success_counts.values()):
        raise ValueError('Exactly two valid binary-success diagnostic cases per task are required')
    return 3*success_counts['BP']-success_counts['DO']-success_counts['DC']-success_counts['PU']


def candidates():
    rules=[{'id':'always_keep','kind':'constant','action':'keep'}, {'id':'always_switch','kind':'constant','action':'switch'}]
    for direction,boundaries in [('high',range(11,-12,-2)),('low',range(-11,12,2))]:
        for b in boundaries:
            rules.append({'id':f'{direction}_{b:+03d}_over12','kind':'threshold','direction':direction,'threshold_numerator_over12':b})
    return rules


def action(rule,q):
    if type(q) is not int or q not in range(-6,7): raise ValueError('Invalid diagnostic score')
    if rule['kind']=='constant': return rule['action']
    b=rule['threshold_numerator_over12']
    yes=2*q>b if rule['direction']=='high' else 2*q<b
    return 'switch' if yes else 'keep'


def validate_rows(rows):
    counts=Counter(row['original_seed'] for row in rows)
    if not counts or any(n!=2 for n in counts.values()): raise ValueError('Two distinct 8k states per parent required')
    if len({(r['original_seed'],r['continuation']) for r in rows})!=len(rows): raise ValueError('Duplicate development state')
    for row in rows:
        action(candidates()[0],row['q'])
        for key in ('keep_successes','switch_successes'):
            if type(row[key]) is not int or not 0<=row[key]<=400: raise ValueError('Full four-task O100 success counts required')


def fit_rule(rows):
    """Equal-parent objective is exact total successes because every parent has two states."""
    validate_rows(rows)
    fitted=[]
    for index,rule in enumerate(candidates()):
        actions=[action(rule,r['q']) for r in rows]
        total=sum(row[a+'_successes'] for row,a in zip(rows,actions))
        switches=actions.count('switch'); complexity=int(rule['kind']=='threshold')
        fitted.append(((total,-switches,-complexity,-index),rule))
    return max(fitted,key=lambda item:item[0])[1].copy()


def lopo(rows):
    """Conditional on F*/A* chosen in stage 1; not full-pipeline independent validation."""
    validate_rows(rows); parents=sorted({r['original_seed'] for r in rows})
    if len(parents)<2: raise ValueError('Need multiple parents for LOPO')
    predictions=[]
    for p in parents:
        rule=fit_rule([r for r in rows if r['original_seed']!=p])
        for row in rows:
            if row['original_seed']!=p: continue
            chosen=action(rule,row['q']); selected=row[chosen+'_successes']
            predictions.append({'original_seed':p,'continuation':row['continuation'],'rule_id':rule['id'],
                'action':chosen,'vs_keep_pp':(selected-row['keep_successes'])/4,
                'vs_switch_pp':(selected-row['switch_successes'])/4})
    return predictions
