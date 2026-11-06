"""The frozen offline onset rule, indexed by control results x_0,...,x_L."""
from __future__ import annotations
import hashlib
import json
import numpy as np

def centered_median(x):
    x = np.asarray(x, dtype=np.float64)
    result = np.full(len(x), np.nan)
    if len(x) >= 3:
        result[1:-1] = np.median(np.stack((x[:-2], x[1:-1], x[2:])), axis=0)
    return result

def detect(d, q, sigma, s_goal=-1):
    """Do not skip the first distance/stationarity candidate for any later candidate.

    Even early-excluded episodes retain the first candidate as a diagnostic. They
    can never supply a window to the treatment archive.
    """
    d = np.asarray(d, dtype=np.float64); q = np.asarray(q, dtype=np.float64)
    if d.ndim != 1 or d.shape != q.shape: raise ValueError('d and q must be x0..xL scalar series')
    L = len(d) - 1
    result = dict(L=L, sigma=int(sigma) if sigma is not None else None, tau=None,
        eligible=False, reasons=[], early_progress_without_context=False,
        stationary_joint_range_m=None, first_decrease_m=None, eight_action_progress_m=None,
        hold_min_progress_m=None, signed_joint_progress_m=None,
        P_start=None, P_end=None)
    if L < 1 or not np.isfinite(d).all() or not np.isfinite(q).all():
        result['reasons'].append('missing_x0_or_joint'); return result
    early = d[0] - d[1:min(16,L)+1]
    result['early_max_raw_progress_m'] = float(early.max())
    result['early_progress_without_context'] = bool(np.any(early >= .005))
    if result['early_progress_without_context']: result['reasons'].append('early_progress_without_context')
    if sigma is None:
        result['reasons'].append('not_success'); return result
    dt = centered_median(d); qt = centered_median(q)
    for tau in range(6, min(int(sigma)-1, L-11)+1):
        stationary = float(np.ptp(qt[tau-5:tau]))
        first = float(dt[tau-1]-dt[tau])
        eight = float(dt[tau-1]-dt[tau+7])
        hold = dt[tau-1]-dt[tau+8:tau+11]
        if stationary <= .001 and first >= .0001 and eight >= .005 and np.all(hold >= .0025):
            signed = float(s_goal*(qt[tau+7]-qt[tau-1]))
            result.update(tau=tau, stationary_joint_range_m=stationary, first_decrease_m=first,
                eight_action_progress_m=eight, hold_min_progress_m=float(hold.min()),
                signed_joint_progress_m=signed, P_start=tau-16, P_end=tau+15)
            if not signed > 0: result['reasons'].append('signal_inconsistent')
            if tau < 17: result['reasons'].append('left_window_incomplete')
            if tau+15 > L: result['reasons'].append('right_window_incomplete')
            if tau+15 >= sigma: result['reasons'].append('window_reaches_first_success')
            break
    if result['tau'] is None: result['reasons'].append('no_qualifying_onset')
    result['eligible'] = len(result['reasons']) == 0
    return result

def derived_seed(*parts):
    encoded = json.dumps(list(parts), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], 'little')

def random_pre_start(protocol_version, donor_run, permanent_episode_id, sigma):
    seed = derived_seed(protocol_version, donor_run, str(permanent_episode_id), 41031)
    rng = np.random.Generator(np.random.PCG64(seed))
    return int(rng.integers(1, int(sigma)-31)), seed

def synthetic_checks():
    checks = []
    def check(name, truth, detail=''):
        checks.append(dict(check=name, passed=bool(truth), detail=detail, scope='synthetic, not scientific data'))
        if not truth: raise AssertionError(name+': '+str(detail))
    def series(tau, L=140):
        t=np.arange(L+1); q=-.001*np.clip(t-tau+1,0,20); return .19+q,q
    d,q=series(40); r=detect(d,q,130)
    check('clear onset uses exact first candidate and 32 original transitions',r['eligible'] and r['tau']==40 and r['P_end']-r['P_start']+1==32,str(r))
    check('no progression has no candidate',detect(np.full(141,.19),np.zeros(141),130)['tau'] is None)
    d,q=series(10); r=detect(d,q,130)
    check('early first candidate excluded, never replaced by a later event',not r['eligible'] and r['tau']==10 and 'early_progress_without_context' in r['reasons'] and 'left_window_incomplete' in r['reasons'])
    d=np.full(141,.19);q=np.zeros(141);d[40]=.18;q[40]=-.01
    check('single sample spike removed by median and hold requirement',detect(d,q,130)['tau'] is None)
    d,q=series(100);r=detect(d,q,115)
    check('window excludes the first official success transition',r['tau']==100 and not r['eligible'] and 'window_reaches_first_success' in r['reasons'])
    d,q=series(40); q=-q; r=detect(d,q,130)
    check('inconsistent first candidate is excluded without next-candidate substitution',r['tau']==40 and 'signal_inconsistent' in r['reasons'] and not r['eligible'])
    for sigma in (33,34,55,500):
        j,s=random_pre_start('fixture','R01','1',sigma)
        check('random prefix integer support '+str(sigma),1<=j<=sigma-32 and j+31<sigma)
    check('permanent episode random window is order independent',random_pre_start('v1','R02','9',210)==random_pre_start('v1','R02','9',210))
    check('AUC weights and new budget arithmetic',sum([.125,.25,.375,.25])==1 and 5*2*3*64000==1920000 and 30*3*64*500+5*64*500+1920000+10000==4970000)
    return checks
