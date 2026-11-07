"""File-only publication88 helpers; isolated Git store, no learner imports."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
VERSION='87_bp_retention_archive_content_posthoc_v1';TOOL=HERE.name
PUBLIC='09_experience_reuse_pilots/'+VERSION
PUBLIC_TOOL='07_operations_and_publication/'+TOOL
V85='09_experience_reuse_pilots/85_onset_reuse_pilot_v1'
A85=V85+'/results/20261106T042248Z_onset_campaign_24d98d21/analysis/20261106T111509Z_paired_3db89d3f'
OLD_STORE=ROOT/'86_onset_reuse_results_publication_v1/results/20261106T113621Z_publication_63a9d339/object_store.git'
REMOTE='https://github.com/rlatmddn0211/practice_allocation.git'
ZERO=dict(environment_creations=0,resets=0,environment_transitions=0,environment_restores=0,mujoco_forward=0,
    model_loads=0,policy_forwards=0,learning_updates=0,new_bootstrap_draws=0)
FORBIDDEN={'torch','mujoco','metaworld','gym','gymnasium','stable_baselines3','tensorflow','jax'}

def guard():
    def audit(event,args):
        if event=='import' and str(args[0]).split('.')[0] in FORBIDDEN:raise RuntimeError('Publication88 is file-only')
    sys.addaudithook(audit)

def utc():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def command(args,data=None,env=None):
    r=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,env=env)
    if r.returncode:raise RuntimeError(repr(args)+'\n'+r.stderr.decode('utf-8','replace'))
    return r.stdout
def git(bare,*args,data=None,env=None):
    clean=(env or os.environ).copy()
    for k in ('GIT_INDEX_FILE','GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES'):clean.pop(k,None)
    return command(['git','-c','core.longpaths=true','--git-dir='+str(bare),*args],data,clean)
def entries(bare,ref):
    out={}
    for row in git(bare,'ls-tree','-rz',ref).split(b'\0'):
        if not row:continue
        head,path=row.split(b'\t',1);mode,kind,oid=head.decode().split()
        if kind!='blob':raise RuntimeError('Unexpected tree entry')
        out[path.decode('utf-8')]=(mode,oid)
    return out
def runtime_state():
    gd=Path(command(['git','rev-parse','--path-format=absolute','--git-common-dir']).decode().strip())
    return dict(head=command(['git','rev-parse','HEAD']).decode().strip(),index_sha256=sha(gd/'index'),
        readme_sha256=sha(ROOT/'README.md'),agents_sha256=sha(ROOT/'AGENTS.md'))

guard()
