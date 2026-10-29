"""Publish only existing retention video examples and a scoped root README."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback
import uuid
from datetime import datetime,timezone
import imageio.v2 as imageio
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=ROOT/'72_saved_video_review_v1/results/20261029T063540Z_review_3a5dcc4d/pairs.json'
SPECS=[('bp_d_better','BP',41014,1,64,'01','BP 사례: D 성공·C 실패'),
       ('bp_c_better','BP',41011,1,7,'10','반대 BP 사례: C 성공·D 실패'),
       ('dc_d_better','DC',41013,1,24,'01','DC 사례: D 성공·C 실패'),
       ('dc_c_better','DC',41011,1,17,'10','반대 DC 사례: C 성공·D 실패')]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p),'bytes':Path(p).stat().st_size}
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def repo(p):return Path(p).resolve().relative_to(ROOT).as_posix()

def preview(pair,arm,dest):
    item=pair[arm];metadata=read(item['result']['path']);reader=imageio.get_reader(item['video']['path'])
    source_frames=[reader.get_data(i) for i in range(len(metadata['frames']))];reader.close()
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',14)
    headerfont=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',15)
    horizon=max(pair['C']['length'],pair['D']['length']);frames=[]
    targets=list(range(0,horizon+1,10))
    if targets[-1]!=horizon:targets.append(horizon)
    for step in targets:
        observed=min(step,item['length'])
        idx=max(i for i,r in enumerate(metadata['frames']) if r['step']<=observed)
        frame=Image.new('RGB',(320,288),'#eef2f7');im=Image.fromarray(source_frames[idx])
        ended=step>=item['length']
        if step>item['length']:im=Image.blend(im,Image.new('RGB',im.size,'#e5e7eb'),.45)
        frame.paste(im,(0,30));draw=ImageDraw.Draw(frame)
        title='C · 일반 경험 보호' if arm=='C' else 'D · 성공 경험 우선 보호'
        draw.text((8,3),title,font=headerfont,fill='#132338')
        detail=f"{pair['task']} · 관측 {min(step,item['length'])}/{item['length']} step"
        if ended:detail+=' · '+('성공 종료' if item['success'] else '미성공 종료')
        draw.text((7,269),detail,font=font,fill='#22364c')
        if step>item['length']:
            draw.rectangle((30,120,290,166),fill='#f3f4f6')
            draw.text((58,132),'관찰 종료 · 이후 상태 미측정',font=font,fill='#334155')
        frames.append(frame.quantize(colors=128,method=Image.Quantize.MEDIANCUT))
    frames[0].save(dest,save_all=True,append_images=frames[1:],duration=[125]*(len(frames)-1)+[1000],loop=0,disposal=2,optimize=False)
    with Image.open(dest) as f:
        if f.n_frames<2 or f.size!=(320,288):raise RuntimeError('Invalid animated preview')
    if dest.stat().st_size>=10*1024**2:raise RuntimeError('GIF exceeds publication size limit')
    return {'source_encoded_frames':len(source_frames),'preview_frames':len(frames),
            'preview_fps':8,'final_hold_ms':1000,'display_horizon_step':horizon,
            'post_observation':'last actually recorded frame shaded and labeled observation ended; no future state synthesized'}

def section(out,cases):
    media=repo(out/'media');record=repo(out/'publication_record_ko.md')
    lines=['<!-- retention-video-publication:start -->','## 일반 경험 보호와 성공 경험 우선 보호','',
        '추가 학습 중 **어떤 경험의 행동을 보호하느냐**를 비교한 개발 실험이다. 두 방법 모두 추가 학습 시작 정책 **S(208k)**를 고정 교사로 사용한다. '
        '같은 관측에서 교사와 현재 정책의 행동 분포 차이 `KL(교사 || 현재)`를 actor 손실에 더한다(계수 1). '
        '이때 보호하는 것은 해당 관측에서의 행동 분포이며 성공 라벨 자체가 아니다.','',
        '| 조건 | 보호할 관측을 고르는 방식 | 학습에서 하는 일 |','|---|---|---|',
        '| **C · 일반 경험 보호** | 성공 여부로 우선순위를 주지 않고 일반 훈련 경험에서 관측을 선택 | 고정 S 교사의 행동 분포와 현재 정책의 차이를 제한 |',
        '| **D · 성공 경험 우선 보호** | 과거 성공 episode에 속한 관측을 우선 선택. 해당 과제·시기 층에 성공 자료가 없으면 C와 동일한 일반 자료로 대체 | C와 같은 행동 보존 손실 적용 |','',
        '과제·경험 생성 시기(25k 구간)·episode/관측 할당과 실제 보호 표집 횟수를 맞췄다. '
        '같은 계수가 실제 제약의 크기·방향까지 같게 만든다는 뜻은 아니다. '
        '**D는 SAC의 replay에서 성공 경험을 더 자주 뽑아 RL 업데이트하는 방법이 아니다.** '
        '원래 RL replay·critic·entropy 업데이트는 유지하고 별도 보호 관측으로 actor를 정규화한다. '
        'C에도 성공 경험이 포함될 수 있고, 성공 episode의 모든 관측이 공유 기초 동작으로 식별된 것은 아니다.','',
        '### 같은 출발 상태·같은 평가 사례의 영상','',
        '기존 Meta-World B의 BP(Button Press)와 DC(Drawer Close) 예시다. '
        'P는 200k 이전 기준, S는 BP 집중 8k 후의 208k 출발점이며, 아래 C/D 최종 정책은 각각 32k를 더 학습한 240k 정책이다. '
        '같은 부모·기존 미래 N1·초기 상태·goal·평가 seed로 비교했다. '
        '아래 GIF를 누르면 각 정책의 **전체 MP4**를 열 수 있다. 미리보기는 별도 재생되므로 정확한 시점 비교는 표시된 step과 MP4를 기준으로 한다.','',
        '**영상 출처:** 새 기능 진단에서 저장한 수치 상태를 고정 카메라로 다시 시각화한 영상이다. '
        '새 rollout이나 정책 실행을 생성하지 않았다. 성공이 처음 관찰되면 평가가 종료되며, '
        '미리보기의 짧은 영상 뒤는 관찰 종료로 표시한다. 그 뒤의 행동이 유지되거나 실패했다고 채워 넣지 않는다.','']
    for i,c in enumerate(cases):
        if i:lines+=['<details>',f'<summary>{c["title"]}</summary>','']
        else:lines+=['#### '+c['title'],'']
        lines +=[f"부모 **{c['parent']}**, 미래 **N{c['future']}**, 과제 **{c['task']}**, 물리 사례 **{c['episode_index']}**.",'',
            '| C · 일반 경험 보호 | D · 성공 경험 우선 보호 |','|:---:|:---:|',
            f"| [![C: {c['title']}]({media}/{c['slug']}_C.gif)]({media}/{c['slug']}_C.mp4) | [![D: {c['title']}]({media}/{c['slug']}_D.gif)]({media}/{c['slug']}_D.mp4) |",
            f"| **{'성공' if c['C']['success'] else '미성공'} · {c['C']['length']} step** · [전체 MP4]({media}/{c['slug']}_C.mp4) | **{'성공' if c['D']['success'] else '미성공'} · {c['D']['length']} step** · [전체 MP4]({media}/{c['slug']}_D.mp4) |",'']
        if i==0:lines+=['이 사례에서 D는 40step에 성공했고 C는 버튼 부근까지 이동했지만 500step까지 성공하지 못했다. 접근만으로 성공 여부를 설명할 수 없다는 예시이며, 정확한 접촉 원인은 영상만으로 판정하지 않는다.','']
        elif i==1:lines+=['반대 방향의 BP 사례다. C는 38step에 성공했지만 D는 500step까지 성공하지 못했다. 성공 경험 우선 보호가 모든 사례에 유리한 것은 아니다.','']
        elif i==2:lines+=['DC에서 D가 빠르게 성공한 사례다. 성공 정책의 짧은 관찰 구간을 500step 동안의 안정적 보존으로 해석하지 않는다.','']
        else:lines+=['반대 방향의 DC 사례다. C는 성공했지만 D는 대상에서 벗어나는 움직임과 함께 미성공으로 끝났다. 기능 능력의 영구적 상실을 입증하는 영상은 아니다.','']
        if i:lines+=['</details>','']
    lines +=['### 현재 결과의 범위','',
        '[68번 결과](68_retention_intervention_result_review_v1/results/20261028T072607Z_review_323af171/report_ko.md)의 원래 네 과제 평균 D−C는 **+2.55%p** '
        '(개별 조건부 사례 95% 구간 **[+1.499, +3.650]**), BP는 **+11.8%p**, DC는 **−2.4%p**였다. '
        'D−기본 SAC는 네 과제 평균 **+1.10%p [−0.25, +2.45]**로 일반적 총성능 우위는 미확정이다. '
        '이 숫자들은 영상 예시의 평균이 아니다.','',
        '영상은 기존 결과를 알고 고른 **양방향 설명용 사례**다. 전체 빈도를 대표하지 않으며, '
        '성공의 인과적 기전이나 공유 기초 동작의 보존을 확인한 자료로 취급하지 않는다. '
        f'[영상별 출처·해시·복사 및 인코딩 규칙]({record})을 함께 공개했다.','',
        '<!-- retention-video-publication:end -->','']
    return '\n'.join(lines)

def main():
    out=HERE/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_prepare_'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    (out/'source_snapshot').mkdir();(out/'media').mkdir();(out/'inputs').mkdir()
    for n in ('prepare.py','README.md'):shutil.copy2(HERE/n,out/'source_snapshot'/n)
    save(out/'source_hashes.json',{n:sha(HERE/n) for n in ('prepare.py','README.md')})
    try:
        if git('diff','--cached','--name-only').strip():raise RuntimeError('Pre-existing staged changes; preserve them')
        if git('rev-parse','HEAD')!=git('rev-parse','origin/main'):raise RuntimeError('Remote main differs; synchronize safely first')
        pairs=read(SOURCE);cases=[];assets=[];input_refs={'source_pairs':ref(SOURCE)}
        for slug,task,parent,future,idx,group,title in SPECS:
            pair=next(p for p in pairs if (p['task'],p['parent'],p['future'],p['episode_index'])==(task,parent,future,idx))
            if pair['group']!=group:raise RuntimeError('Frozen source outcome group changed')
            if pair['C']['initial_state_hash']!=pair['D']['initial_state_hash']:raise RuntimeError('Physical case pairing changed')
            case={'slug':slug,'title':title,'parent':parent,'task':task,'future':future,'episode_index':idx,'group':group}
            for arm in ('C','D'):
                item=pair[arm]
                for name in ('video','episode','result'):
                    if sha(item[name]['path'])!=item[name]['sha256']:raise RuntimeError('Input changed: '+name)
                ep=read(item['episode']['path'])
                if (ep['parent'],ep['task'],ep['future'],ep['episode_index'],ep['success'],ep['length'])!=(parent,task,future,idx,item['success'],item['length']):raise RuntimeError('Episode/video metadata mismatch')
                mp4=out/'media'/(slug+'_'+arm+'.mp4');gif=out/'media'/(slug+'_'+arm+'.gif')
                shutil.copy2(item['video']['path'],mp4)
                if sha(mp4)!=item['video']['sha256']:raise RuntimeError('MP4 not a byte-identical copy')
                p=preview(pair,arm,gif)
                for name in ('episode','result'):
                    target=out/'inputs'/(slug+'_'+arm+'_'+name+'.json');shutil.copy2(item[name]['path'],target)
                case[arm]={'success':item['success'],'length':item['length'],'episode':item['episode'],'video_source':item['video'],'result':item['result'],
                    'published_mp4':ref(mp4),'published_preview':ref(gif),'preview':p}
                assets.extend([ref(mp4),ref(gif)])
            cases.append(case)
        save(out/'cases.json',cases);save(out/'input_receipt.json',input_refs)
        record=['# README 영상 공개 기록','',
            '사용자 요청에 따라 C/D 조건 설명과 BP/DC의 양방향 사례4쌍을 공개한다. 새 환경·정책·MuJoCo·학습·재표집은0이다.',
            'MP4는 기존 고정 카메라 보조영상의 바이트 동일 사본이며 원래 rollout 중 영상은 그대로 로컬에 보존했다.',
            'GIF는 압축한 미리보기다. 비교 쌍의 긴 구간에 맞춰 표시하되 짧은 정책의 관찰 종료 뒤는 실제 마지막 frame을 흐리게 하고 미측정으로 표시한다.',
            '끝에1초를 더 보여주는 것은 표시용 hold이며 추가 학습·평가 시간이 아니다. 원래 step과 성공 판정은 수정하지 않았다.',
            '', '| 과제 | 부모 | 미래 | 사례 | C 성공/step | D 성공/step |','|---|---:|---:|---:|---|---|']
        for c in cases:record.append(f"| {c['task']} | {c['parent']} | N{c['future']} | {c['episode_index']} | {c['C']['success']}/{c['C']['length']} | {c['D']['success']}/{c['D']['length']} |")
        record+=['','cases.json은원MP4/episode/result와배포사본의SHA256을보존한다. inputs의episode/result는동일사본이다.',
            'original local source paths in those records refer to retained research assets; publishing these examples is not a full checkpoint/data backup.',
            '','이번게시에는69/71/72전체파일,체크포인트,추가연구실행을포함하지않는다. 원래66/68자료와결론은유지한다.']
        (out/'publication_record_ko.md').write_text('\n'.join(record)+'\n',encoding='utf-8')
        block=section(out,cases);(out/'readme_section.md').write_text(block,encoding='utf-8')
        working=(ROOT/'README.md').read_text(encoding='utf-8')
        if '<!-- retention-video-publication:start -->' in working:raise RuntimeError('Video section already exists; preserve existing publication')
        old_intro='추가 강화학습에서 성공을 얻는 사례의 패턴이 출발 학습 상태에 얼마나 의존하며,\n그 의존성이 새로운 학습 미래와 새로운 부모·상태에서도 유지되는지\n\n'
        introduction='추가 학습에서 무엇을 어떻게 보호해야 기존 성공의 상실을 줄이면서,\n다른 사례의 성공 획득과 이전 성공의 회복을 유지할 수 있는지 연구합니다.\n\n'
        published=git('show','HEAD:README.md').decode('utf-8').replace(old_intro,'')
        published=published.replace('# Robot practice allocation\n\n','# Robot practice allocation\n\n'+introduction+block+'\n',1)
        (out/'published_README.md').write_text(published,encoding='utf-8',newline='\n')
        save(out/'prepublication_state.json',{'base_commit':git('rev-parse','HEAD').decode().strip(),'local_readme_before':ref(ROOT/'README.md'),
            'local_agents_preserved':ref(ROOT/'AGENTS.md'),'publication_readme':ref(out/'published_README.md'),
            'new_environment_steps':0,'media_assets':assets,'unrelated_directories_excluded':[69,71,72]})
        # Explicitly authorized working README change; all its other local additions survive.
        (ROOT/'README.md').write_text(working.replace('설계 기준:',block+'\n설계 기준:',1),encoding='utf-8',newline='\n')
        save(out/'summary.json',{'status':'prepared','cases':4,'mp4_files':8,'gif_files':8,'media_bytes':sum(x['bytes'] for x in assets),
            'published_readme':ref(out/'published_README.md'),'local_readme_after':ref(ROOT/'README.md'),
            'new_environment_steps':0,'new_training_steps':0,'new_policy_or_mujoco_calls':0})
        save(out/'COMPLETE.json',{'summary':ref(out/'summary.json')})
        print(json.dumps({'publication_dir':str(out),'published_readme':str(out/'published_README.md')}))
    except BaseException:
        save(out/'FAILED.json',{'traceback':traceback.format_exc(),'new_environment_steps':0});raise

if __name__=='__main__':main()
