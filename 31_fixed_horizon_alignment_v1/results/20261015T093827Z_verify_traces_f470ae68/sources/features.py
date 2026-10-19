"""Fixed-horizon diagnostics; calibrations trained excluding entire original seed."""
from pathlib import Path
from collections import defaultdict
import numpy as np
from common import ROOT,save,table
from performance_controls import PROFILE,role

BASE=PROFILE+['reward_scale','target_scale','residual','gap']
SUCCESS=BASE+['new_p0_focus','new_p0_other','new_p20_focus','new_p20_other']
ROLLOUT=SUCCESS+['mc_scale_focus','mc_scale_other','mc_se_focus','mc_se_other']
GROUPS={'CriticBase':BASE,'SuccessBase':SUCCESS,'RawReturn':SUCCESS+['return_focus','return_other'],
        'CalibratedReturn':SUCCESS+['cal_gap_focus','cal_gap_other'],
        'RolloutBase':ROLLOUT,'RolloutValue':ROLLOUT+['mc_error_focus','mc_error_other'],
        'NearObject':SUCCESS+['near_focus','near_other']}
FOLD_FIELDS=['return_focus','return_other','cal_gap_focus','cal_gap_other']


def calibrated_fit(values,success):
    x=np.asarray(values);y=np.asarray(success);mu=float(x.mean());sd=float(x.std());sd=sd if sd>1e-12 else 1.
    z=(x-mu)/sd;intercept=float(y.mean());slope=float(np.mean(z*(y-intercept))/(1+np.mean(z*z)))
    return {'mean':mu,'scale':sd,'intercept':intercept,'slope':slope,'penalty':1.}


def prepare_fold(rows,held):
    return [dict(r,**{field:r[field+'_held'+str(held)] for field in FOLD_FIELDS}) for r in rows]


def build(run,p,parents,ys,lengths,splits,refs,measurement=None):
    if not measurement:raise ValueError('Campaign directory required')
    cam=Path(measurement);integrity=run.read(cam/'plan_integrity.json');plan=run.read(cam/'plan.json',integrity['sha256'])
    diags={};metadata={};mcstats={};newsteps=0
    for job in plan['jobs']:
        if job['stage']!='F05' or job['kind']!='measure':continue
        marker=run.read(cam/'completed'/(job['id']+'.json'));rec=run.read(marker['result_ref']['path'],marker['result_ref']['sha256'])
        jid=rec['original_id'];run.check('model identity '+jid,rec['checkpoint']==refs[jid] and rec['learner_unchanged'])
        run.hashed(rec['episodes_path'],rec['episodes_sha256']);run.hashed(rec['mc_path'],rec['mc_sha256']);run.hashed(rec['traces_path'],rec['traces_sha256'])
        dd=run.rows(rec['episodes_path']);mm=run.rows(rec['mc_path']);run.check('80 D32 MC '+jid,len(dd)==80 and len(mm)==32)
        diags[jid]=dd;metadata[jid]=job;newsteps+=rec['new_environment_steps'];taskstats={}
        for task in p['suites'][job['suite']]:
            rr=[r for r in mm if r['task']==task];est=np.array([float(r['soft_return']) for r in rr]);scale=max(float(np.sqrt(np.mean(est**2))),1.)
            errors=[];ses=[];tailfree=[]
            for case in [0,1]:
                sub=[r for r in rr if int(r['episode_index'])==case];values=np.array([float(r['soft_return']) for r in sub]);qq=float(sub[0]['q_min'])
                errors.append(abs(qq-values.mean())/scale);ses.append(float(values.std(ddof=1)/2)/scale)
                tailfree.append(abs(qq-np.mean([float(r['tail_free_return']) for r in sub]))/scale)
            taskstats[task]={'error':float(np.mean(errors)),'scale':float(np.log1p(scale)),'se':float(np.mean(ses)),
                             'tailfree_error':float(np.mean(tailfree)),'relative_tail':float(np.mean([abs(float(r['discounted_tail'])) for r in rr])/scale)}
        mcstats[jid]=taskstats
    run.check('all192 matched diagnostics',len(diags)==192 and newsteps==p['planned_environment_steps'])
    inv=run.rows(ROOT/p['prior_artifact_manifest']);expected={str((ROOT/'29_neural_plasticity_screening_v1'/r['path']).resolve()):r['sha256'] for r in inv}
    path=ROOT/p['prior_features'];run.hashed(path,expected[str(path.resolve())]);old=run.rows(path)
    calibration={}
    all_tasks=sorted({t for tasks in p['suites'].values() for t in tasks})
    for held in p['original_seeds']:
        calibration[held]={}
        for task in all_tasks:
            train=[(jid,r) for jid,dd in diags.items() if metadata[jid]['original_seed']!=held for r in dd if r['task']==task]
            ff=calibrated_fit([float(r['return500']) for _,r in train],[float(r['success']) for _,r in train])
            ff['train_ids']=sorted({jid for jid,_ in train});ff['n_episodes']=len(train);calibration[held][task]=ff
    save(run.out/'calibrations.json',calibration)
    result=[]
    for prev in old:
        r={k:float(v) for k,v in prev.items() if k in BASE+['D20','target_D_remainder','O40','weight']}
        r.update({k:prev[k] for k in ['id','suite','allocation']});r.update({k:int(prev[k]) for k in ['original_seed','checkpoint_step','continuation']})
        jid=r['id'];parent=jid.split('_r')[0]+'_base';tasks=p['suites'][r['suite']];ai=0 if r['allocation']=='U' else tasks.index(r['allocation'][2:])+1
        rr0={t:[x for x in diags[parent] if x['task']==t] for t in tasks};rr1={t:[x for x in diags[jid] if x['task']==t] for t in tasks}
        for prefix,data in [('new_p0',rr0),('new_p20',rr1)]:
            f,o=role(np.array([np.mean([float(x['success']) for x in data[t]]) for t in tasks]),ai);r[prefix+'_focus']=f;r[prefix+'_other']=o
        f,o=role(np.array([np.mean([float(x['near_object_reached']) for x in rr1[t]]) for t in tasks]),ai);r['near_focus']=f;r['near_other']=o
        for name in ['scale','se','error']:
            f,o=role(np.array([mcstats[jid][t][name] for t in tasks]),ai);r['mc_'+name+'_focus']=f;r['mc_'+name+'_other']=o
        for held in p['original_seeds']:
            delta=[];gap=[]
            for task in tasks:
                ff=calibration[held][task];x0=np.array([float(x['return500']) for x in rr0[task]]);x1=np.array([float(x['return500']) for x in rr1[task]])
                predict=lambda x:np.clip(ff['intercept']+ff['slope']*(x-ff['mean'])/ff['scale'],0,1)
                delta.append((x1.mean()-x0.mean())/ff['scale'])
                actual=np.mean([float(x['success']) for x in rr1[task]])-np.mean([float(x['success']) for x in rr0[task]])
                gap.append(float(predict(x1).mean()-predict(x0).mean()-actual))
            for name,values in [('return',delta),('cal_gap',gap)]:
                f,o=role(np.array(values),ai);r[name+'_focus_held'+str(held)]=f;r[name+'_other_held'+str(held)]=o
        result.append(r)
    table(run.out/'rollout_value_task_diagnostics.csv',[{'id':jid,'task':t,**v} for jid,rows in mcstats.items() for t,v in rows.items()])
    alignment=[]
    for held,cc in calibration.items():
        for task,ff in cc.items():
            rr=[r for jid,rows in diags.items() if metadata[jid]['original_seed']==held for r in rows if r['task']==task]
            pr=np.clip(ff['intercept']+ff['slope']*(np.array([float(r['return500']) for r in rr])-ff['mean'])/ff['scale'],0,1);y=np.array([float(r['success']) for r in rr])
            alignment.append({'held_original_seed':held,'task':task,'episodes':len(rr),'Brier':float(np.mean((pr-y)**2)),
                              'constant_Brier':float(np.mean((ff['intercept']-y)**2)),'slope':ff['slope']})
    table(run.out/'held_seed_return_calibration.csv',alignment)
    return result,{'snapshots':len(diags),'new_diagnostic_environment_steps':newsteps,'persistent_updates':0,
                   'calibration':'task-specific, original-seed-excluded; clipped ridge linear probability',
                   'rollout_note':'finite500step soft estimate with16draw currentQ tail,4 sampled trajectories/initial state; not exact value'}
