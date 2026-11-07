"""Independent scalar arithmetic and raw count-boundary checks for87 outputs."""
from __future__ import annotations
from common import *
guard()
import argparse
import numpy as np
import pandas as pd
from exposure import FEATURES


def run(analysis):
    analysis=Path(analysis).resolve();out=analysis/'verification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    shutil.copy2(__file__,out/'source.py');inputs=Inputs();checks=Checks();started=time.perf_counter()
    try:
        original=inputs.parquet(ANALYSIS/'checkpoint_case_history.parquet','original85 labels for independent scalar re-count')
        old=original[original.task_id=='BP'];new=inputs.parquet(analysis/'bp_arm_histories.parquet','87 complete histories')
        keys=['parent_id','future_id','arm','physical_case_id']
        j=old.merge(new,on=keys,suffixes=('_old','_new'),validate='one_to_one')
        checks.add('480 rows retained, all old labels unchanged',len(j)==480 and all(np.array_equal(j[c+'_old'],j[c+'_new']) for c in ['z0','z16','z32','z64']))
        totals={a:dict(gain=0,loss=0,recovery=0,initial=0,final=0,all_four=0,initial_recovered=0) for a in ARMS}
        for r in new.to_dict('records'):
            z=[int(r[c]) for c in ['z0','z16','z32','z64']];g=l=rec=0;seen=bool(z[0])
            for before,after in zip(z[:-1],z[1:]):
                if before==0 and after==1:g+=1;rec+=int(seen)
                if before==1 and after==0:l+=1
                seen=seen or bool(after)
            checks.add('scalar event/history '+r['history_id'],g==r['gain_events'] and l==r['loss_events'] and rec==r['recovery_events'])
            if any(z):
                first=z.index(1);checks.add('first acquisition opportunities '+r['history_id'],r['first_success_train_step']==TIMES[first] and r['subsequent_evaluation_opportunities']==3-first)
            q=totals[r['arm']];q['gain']+=g;q['loss']+=l;q['recovery']+=rec;q['initial']+=z[0];q['final']+=z[-1]
            q['all_four']+=int(all(z));q['initial_recovered']+=int(z[0] and z[-1] and not all(z))
        for arm,expected in [('BASE',(32,75,20,105,87,14)),('RANDOM_PRE',(34,48,24,134,105,20)),('ONSET',(34,37,22,145,113,20))]:
            r=totals[arm];checks.add('BP reference event/risk totals '+arm,(r['gain'],r['loss'],r['recovery'],r['final'],r['all_four'],r['initial_recovered'])==expected and r['initial']==148)
        cp=inputs.parquet(analysis/'bp_case_contrasts.parquet','matched case types and bidirectional outcomes')
        checks.add('three pairs each retain160 fixed histories',cp.groupby('contrast').size().to_dict()=={'P-B':160,'P-U':160,'U-B':160})
        for name,kept,gain,total in [('P-B',32,8,40),('P-U',8,3,11)]:
            x=cp[cp.contrast==name];b=x.initial_success.to_numpy();d=x.method_final.to_numpy()-x.reference_final.to_numpy()
            checks.add('independent matched final decomposition '+name,int(d[b==1].sum())==kept and int(d[b==0].sum())==gain and int(d.sum())==total)
        actual=inputs.parquet(ANALYSIS/'archive_usage_by_checkpoint.parquet','original cumulative actual counts')
        diff=inputs.parquet(analysis/'actual_transition_usage_by_interval.parquet','87 transition interval use')
        feature=inputs.parquet(analysis/'do_transition_content.parquet','immutable source feature vectors')
        ikey=['parent_id','future_id','arm','source_episode_id','window_offset','archive_transition_id']
        for end in TIMES[1:]:
            lo=TIMES[TIMES.index(end)-1];a=actual[(actual.checkpoint==1000000+end)&(actual.arm!='BASE')].set_index(ikey).actor_sample_count
            b=actual[(actual.checkpoint==1000000+lo)&(actual.arm!='BASE')].set_index(ikey).actor_sample_count
            d=diff[diff.interval_end==end].set_index(ikey)
            checks.add('interval actual-count boundary '+str(end),a.index.equals(b.index) and np.array_equal((a-b).sort_index(),d.interval_actor_use.sort_index()))
        output=inputs.csv(analysis/'actual_interval_exposure_features.csv','87 exposure arithmetic')
        for keys,x in diff.groupby(['parent_id','future_id','arm','interval_start','interval_end']):
            parent,future,arm,lo,hi=keys;n=x.interval_actor_use.to_numpy(dtype=int);den=int(sum(map(int,n)))
            r=output[(output.parent_id==parent)&(output.future_id==future)&(output.arm==arm)&(output.interval_end==hi)].iloc[0]
            checks.add('weighted exposure denominator '+str(keys),den==r.actual_uses and abs(r.uses_per_actor_update-den/(hi-lo))<1e-10)
            for f in FEATURES:
                value=math.fsum(int(a)*float(b) for a,b in zip(n,x[f]))/den
                checks.add('scalar weighted feature '+str(keys)+'/'+f,abs(value-r[f])<1e-10)
        windows=inputs.parquet(analysis/'do_window_content.parquet','87 directional window and aftermath features')
        for r in windows.to_dict('records'):
            z=inputs.arrays(r['trajectory_ref'],'original source joint only for independent path verification',fields=['joint_position'],expected=r['source_sha256'])
            # All selected starts exceed1, so pre-window q is actually stored.
            a=int(r['window_start']);e=int(r['window_end']);q=z['joint_position'];p=-q[a-2:e]
            delta=[float(b-a) for a,b in zip(p[:-1],p[1:])];pos=sum(v for v in delta if v>0);neg=-sum(v for v in delta if v<0)
            checks.add('scalar original window opening/closing '+r['archive_window_id'],abs(pos-r['opening_path_m'])<1e-10 and abs(neg-r['closing_path_m'])<1e-10 and abs(pos-neg-r['net_opening_m'])<1e-10)
            post=-q[e:int(r['sigma'])];endpoint=-q[e-1]
            checks.add('scalar original aftermath drawdown '+r['archive_window_id'],abs(max(0,float(endpoint-post.min()))-r['post_endpoint_drawdown_m'])<1e-10)
        link=inputs.parquet(analysis/'exposure_BP_effect_linkage.parquet','87 time-respecting linkage')
        checks.add('90 linkage rows and no future exposure assignment',len(link)==90 and (link.interval_end==link.exposure_latest_allowed_train_step).all())
        for end in TIMES[1:]:
            count=diff[diff.interval_end==end].groupby(['parent_id','future_id','arm']).cumulative_actor_use.sum()
            for r in link[link.interval_end==end].to_dict('records'):
                for role in ['method','reference']:
                    arm=r[role];expected=0 if arm=='BASE' else int(count.loc[(r['parent_id'],r['future_id'],arm)])
                    checks.add('linkage as-of cumulative exposure '+r['parent_id']+'/'+r['future_id']+'/'+r['contrast']+'/'+str(end)+'/'+role,r['cumulative_'+role+'_actual_uses']==expected)
        checks.add('forbidden runtime/model modules absent',not FORBIDDEN&set(sys.modules))
        save(out/'FINAL_STATUS.json',dict(status='passed',checks=len(checks.rows),BP_totals=totals,raw_BP_rescan=False,
            verification_scope='original85 labels/cumulative counts and original25 DO joint series; all BP raw1520 were checked once during extraction',new_execution=ZERO))
        save(analysis/'LATEST_VERIFICATION.json',dict(output=str(out),status='passed'),replace=True)
        print(json.dumps(dict(output=str(out),status='passed',checks=len(checks.rows))),flush=True)
    except BaseException as ex:
        save(out/'FAILED.json',dict(error=repr(ex),new_execution=ZERO));raise
    finally:
        checks.flush(out);inputs.flush(out);save(out/'costs.json',dict(wall_seconds=time.perf_counter()-started,tracked_input_bytes=inputs.bytes_read,new_execution=ZERO))
    return out


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--analysis',type=Path,required=True);a=ap.parse_args();run(a.analysis)
