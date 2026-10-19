"""Held-original-seed prediction and retrospective allocation comparison."""
import argparse
import traceback
from pathlib import Path
import numpy as np
from common import Run,HERE,allocations,contexts,context_weight,prefix,save,table
from outcomes import read_outcomes,cases,macro,task_values
from features import GROUPS,build,prepare_fold

def choose(values):
    return int(np.flatnonzero(np.asarray(values)>=np.max(values)-1e-12)[0])

def fit(rows,cols,held,method):
    rows=prepare_fold(rows,held)
    tr=[r for r in rows if r['original_seed']!=held];te=[r for r in rows if r['original_seed']==held]
    x=np.array([[r[k] for k in cols] for r in tr]);xt=np.array([[r[k] for k in cols] for r in te])
    w=np.array([r['weight'] for r in tr]);w/=w.sum();y=np.array([r['target_D_remainder'] for r in tr])
    mu=w@x;sd=np.sqrt(w@((x-mu)**2));sd=np.where(sd>1e-12,sd,1.);z=(x-mu)/sd;ym=float(w@y)
    beta=np.linalg.solve(z.T@(w[:,None]*z)+np.eye(len(cols)),z.T@(w*(y-ym)))
    pred=ym+(xt-mu)/sd@beta
    return {r['id']:float(r['D20']+v) for r,v in zip(te,pred)}, {'method':method,'held_original_seed':held,'features':cols,
        'train_ids':[r['id'] for r in tr],'test_ids':[r['id'] for r in te],'mean':mu.tolist(),'scale':sd.tolist(),
        'intercept':ym,'coef':beta.tolist(),'penalty':1.}

def avg(rows,k):return float(np.average([r[k] for r in rows],weights=[r['weight'] for r in rows]))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--measurement');args=ap.parse_args();run=Run('analysis')
    try:
        p=run.read(HERE/'protocol.json');parents,ys,lengths,splits,refs=read_outcomes(run,p)
        rows,diagnostics=build(run,p,parents,ys,lengths,splits,refs,args.measurement)
        table(run.out/'features.csv',rows);predictions={};fits=[];errors=[]
        for method,cols in GROUPS.items():
            predictions[method]={}
            for held in p['original_seeds']:
                pr,ff=fit(rows,cols,held,method);predictions[method].update(pr);fits.append(ff)
            errors.append({'method':method,'O40_MAE_pp':sum(r['weight']*abs(predictions[method][r['id']]-r['O40'])*100 for r in rows)})
        save(run.out/'ridge_fits.json',fits);table(run.out/'prediction_metrics.csv',errors)
        table(run.out/'predictions.csv',[{'id':r['id'],'method':m,'predicted40':pr[r['id']],'observed_O40':r['O40']} for m,pr in predictions.items() for r in rows])
        selected=[];methods=['Uniform','Failure','Development_fixed','Greedy20']+list(GROUPS)
        for ctx,y in ys.items():
            s,n,c=ctx;dix,oix=splits[s];names=allocations(p,s)
            fixed=choose(np.mean([macro(ys[o][1],dix).mean(0) for o in ys if o[0]==s and o[2]==c and o[1]!=n],axis=0))
            failure=1+int(np.argmin(task_values(parents[ctx],dix)))
            # Reconstruct parent evaluation duration directly; previously only success was returned.
            from common import campaign,record
            cam,planned=campaign(run);br,_=record(run,cam,planned,prefix(ctx)+'_base')
            parent_rows=run.rows(br['episodes_path']);parent_eval=sum(int(e['length']) for e in parent_rows if int(e['episode_index']) in dix[p['suites'][s].index(e['task'])])
            for mode in ['same_repeat','cross_repeat']:
                for ri,rep in enumerate(p['continuations'][s]):
                    dr=[ri] if mode=='same_repeat' else [j for j in range(3) if j!=ri]
                    choice={'Uniform':0,'Failure':failure,'Development_fixed':fixed,'Greedy20':choose(macro(y[0,dr],dix).mean(0))}
                    for method,pr in predictions.items():
                        choice[method]=choose([np.mean([pr[prefix(ctx)+f'_r{p["continuations"][s][j]}_{a}_t20'] for j in dr]) for a in names])
                    val=macro(y[1,ri],oix)*100
                    for method,ai in choice.items():
                        probes=method not in ['Uniform','Failure','Development_fixed']
                        selected.append({'suite':s,'original_seed':n,'checkpoint_step':c,'continuation':rep,'mode':mode,'method':method,
                            'selected_allocation':names[ai],'allocation_index':ai,'weight':context_weight(ctx)/3,'score_pp':float(val[ai]),
                            'vs_uniform_pp':float(val[ai]-val[0]),'vs_fixed_pp':float(val[ai]-val[fixed]),
                            'absolute_gain_pp':float(val[ai]-macro(parents[ctx],oix)*100),'hindsight_regret_pp':float(val.max()-val[ai]),
                            'max_task_drop_pp':float(max(task_values(parents[ctx],oix)-task_values(y[1,ri,ai],oix))*100),
                            'probe_training_steps':len(dr)*100000 if probes else 0,
                            'total_training_steps':(120000 if mode=='same_repeat' else 240000) if probes else 40000,
                            'parent_D_eval_steps':parent_eval if method not in ['Uniform','Development_fixed','Greedy20'] else 0,
                            'probe_D_eval_steps':int(cases(lengths[ctx][0,dr],dix).sum()) if probes else 0,
                            'new_fixed_D_eval_steps':40000*(1+5*len(dr)) if method in GROUPS and method!='CriticBase' else 0,
                            'new_MC_eval_steps':16000*(1+5*len(dr)) if method in ['RolloutBase','RolloutValue'] else 0})
        key=lambda r:tuple(r[k] for k in ['suite','original_seed','checkpoint_step','continuation','mode'])
        base={key(r):r for r in selected if r['method']==p['primary_comparator']}
        greedy={key(r):r for r in selected if r['method']=='Greedy20'}
        for r in selected:
            r['vs_base_pp']=r['score_pp']-base[key(r)]['score_pp'];r['vs_greedy_pp']=r['score_pp']-greedy[key(r)]['score_pp']
            r['changed_vs_base']=int(r['allocation_index']!=base[key(r)]['allocation_index'])
        table(run.out/'selection_rows.csv',selected)
        metrics=['score_pp','vs_uniform_pp','vs_fixed_pp','vs_base_pp','vs_greedy_pp','absolute_gain_pp','hindsight_regret_pp',
                 'max_task_drop_pp','probe_training_steps','total_training_steps','parent_D_eval_steps','probe_D_eval_steps','new_fixed_D_eval_steps','new_MC_eval_steps']
        aggregates={}
        for fname,split in [('selection_summary',None),('selection_by_seed','original_seed'),('selection_by_group','group')]:
            out=[]
            for mode in ['same_repeat','cross_repeat']:
                for method in methods:
                    rr=[r for r in selected if r['mode']==mode and r['method']==method]
                    parts=[None] if split is None else p['original_seeds'] if split=='original_seed' else ['A200','A400','B200','C200']
                    for part in parts:
                        sub=rr if part is None else [r for r in rr if (r['original_seed'] if split=='original_seed' else r['suite']+str(r['checkpoint_step']//1000))==part]
                        out.append({'mode':mode,'method':method,**({split:part} if split else {}),**{k:avg(sub,k) for k in metrics},
                                    'changed_choices':sum(r['changed_vs_base'] for r in sub),'choices':len(sub)})
            table(run.out/(fname+'.csv'),out);aggregates[fname]=out
        contrasts=[]
        for model,comparator in p['planned_contrasts'].items():
            cmp={key(r):r for r in selected if r['method']==comparator}
            for mode in ['same_repeat','cross_repeat']:
                sub=[dict(r,increment=r['score_pp']-cmp[key(r)]['score_pp'],changed=int(r['allocation_index']!=cmp[key(r)]['allocation_index'])) for r in selected if r['method']==model and r['mode']==mode]
                for scope,parts in [('all',[None]),('original_seed',p['original_seeds']),('group',['A200','A400','B200','C200'])]:
                    for part in parts:
                        rr=sub if part is None else [r for r in sub if (r['original_seed'] if scope=='original_seed' else r['suite']+str(r['checkpoint_step']//1000))==part]
                        contrasts.append({'method':model,'comparator':comparator,'mode':mode,'scope':scope,'part':part,
                            'increment_pp':avg(rr,'increment'),'changed_choices':sum(r['changed'] for r in rr),'choices':len(rr)})
        table(run.out/'planned_contrasts.csv',contrasts)
        rng=np.random.default_rng(p['bootstrap_seed']);draws=p['bootstrap_draws']
        weights={s:rng.multinomial(50,np.full(50,.02),size=(draws,4)) for s in p['suites']};intervals=[]
        pairs=[('CalibratedReturn',comp) for comp in ['SuccessBase','Greedy20','Development_fixed']]+[('RolloutValue',comp) for comp in ['RolloutBase','Greedy20','Development_fixed']]
        for mode in ['same_repeat','cross_repeat']:
            for method,comp in pairs:
                rr=[r for r in selected if r['mode']==mode and r['method']==method]
                cc={key(r):r for r in selected if r['method']==comp};boot=np.zeros(draws);point=0.
                for r in rr:
                    ctx=r['suite'],r['original_seed'],r['checkpoint_step'];s=ctx[0];ri=p['continuations'][s].index(r['continuation'])
                    diff=cases(ys[ctx][1,ri,r['allocation_index']]-ys[ctx][1,ri,cc[key(r)]['allocation_index']],splits[s][1])
                    boot+=r['weight']*100*np.einsum('dti,ti->d',weights[s],diff)/200;point+=r['weight']*100*diff.mean()
                intervals.append({'mode':mode,'method':method,'comparator':comp,'increment_pp':float(point),'case_only_lo_pp':float(np.quantile(boot,.025)),
                                  'case_only_hi_pp':float(np.quantile(boot,.975))})
        table(run.out/'conditional_case_intervals.csv',intervals)
        primary=next(r for r in aggregates['selection_summary'] if r['mode']=='same_repeat' and r['method']==p['primary_model'])
        seeds=[r['vs_base_pp'] for r in aggregates['selection_by_seed'] if r['mode']=='same_repeat' and r['method']==p['primary_model']]
        groups=[r['vs_base_pp'] for r in aggregates['selection_by_group'] if r['mode']=='same_repeat' and r['method']==p['primary_model']]
        report=['# F05 동일 길이 목표 정합성과 rollout 가치 진단','',
                '기존192개 정책에서 새 사례의500-step 진단을 완료했다. 모든 새 진단은 원본 학습 상태를 보존했다. 아래는 기존40k 결과를 이용한 탐색 예측·선택 비교이며 새 원래 seed 확인이나 동일 총예산 온라인 실험이 아니다.','',
                '| 추가 지표 | 비교 기준 | 같은 반복 선택 이득 %p | 다른 반복 선택 이득 %p |',
                '| --- | --- | ---: | ---: |']
        for model,comparator in p['planned_contrasts'].items():
            get=lambda mode:next(r['increment_pp'] for r in contrasts if r['method']==model and r['scope']=='all' and r['mode']==mode)
            report.append(f'| {model} | {comparator} | {get("same_repeat"):+.3f} | {get("cross_repeat"):+.3f} |')
        passed=primary['vs_base_pp']>=1 and sum(v>0 for v in seeds)>=2 and min(groups)>=-2
        report+=['',f'주 비교 CalibratedReturn의 선별 기준 통과: {passed}. 원래 seed11/12/13의 증분은 '+', '.join(f'{x:+.3f}%p' for x in seeds)+'.',
                 '', 'return→성공 보정은 각 평가 fold에서 제외한 원래 seed의 자료를 사용하지 않았다. task별 보상 단위를 표준화한 뒤 보정했고, 예측기는 같은 정보 시점의 성공률 기준과 비교했다.',
                 '', 'RolloutValue는 고정 첫 행동에서 시작해500-step 보상·entropy와 할인된 current-Q tail을 합한 추정과 Q의 차이다. 소수 경로의 표준오차와 target scale을 기준 모형에 포함했다. 정확한 무한 길이 가치 정답으로 해석하지 않는다. tail 없는 민감도와 각 task의 표준오차는 별도 표에 보존했다.',
                 '', 'NearObject는 task별 공식 near_object 도달 비율을 사용한 F03 보조 비교다. 과제마다 거리 기준이 다르고 일부 공식 grasp_success는 상수이므로 이를 보편적인 잡기 단계로 합치지 않았다.',
                 '', '실제 새 환경 진단 비용은10,752,000step이며 지속 학습 update는0회다. 같은 반복 선택을 실제로 재현할 때 성공/return 진단은 부모+5probe에서240k 평가step, 가치 진단은96k 평가step을 더 쓴다. 기존20k probe와 D 평가 비용도 별도다. 이번 진단을 값싼 온라인 특징으로 주장하지 않는다.',
                 '', '[모든 비교](planned_contrasts.csv) · [seed별 선택](selection_by_seed.csv) · [예측 오차](prediction_metrics.csv) · [조건부 구간](conditional_case_intervals.csv) · [task별 가치 추정](rollout_value_task_diagnostics.csv) · [반환 보정](held_seed_return_calibration.csv)',
                 '', '조건부 구간은 O 평가 사례만 재표집하고 정책·예측기·진단·선택은 고정한다. 학습 또는 모형 선택의 불확실성과 세 원래 seed 모집단의 효과를 포함하지 않는다.']
        with (run.out/'report_ko.md').open('x',encoding='utf-8') as f:f.write('\n'.join(report)+'\n')
        run.finish({'status':'completed','factor':p['factor'],'measurement':args.measurement,'feature_rows':len(rows),'diagnostics':diagnostics,
                    'primary':primary,'original_seed_increments_pp':seeds,'group_increments_pp':groups,
                    'operational_screen_pass':primary['vs_base_pp']>=1 and sum(v>0 for v in seeds)>=2 and min(groups)>=-2,
                    'prediction_metrics':errors,'conditional_intervals':intervals,'independent_confirmation':False})
    except Exception:
        run.finish({'status':'failed','traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
