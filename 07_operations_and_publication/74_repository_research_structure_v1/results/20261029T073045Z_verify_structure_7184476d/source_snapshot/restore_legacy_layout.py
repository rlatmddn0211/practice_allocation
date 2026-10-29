"""Restore the published pre-organization tree into a new, empty destination."""
import argparse,hashlib,json,os,shutil
from pathlib import Path

def blob_oid(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def restore(repository,output,manifest=None):
    repository=Path(repository).resolve();output=Path(output).resolve()
    if output.exists():raise RuntimeError('Output exists; no overwrite permitted: '+str(output))
    if manifest is None:
        candidates=list(repository.glob('07_operations_and_publication/74_repository_research_structure_v1/results/*/path_manifest.json'))
        if len(candidates)!=1:raise RuntimeError('Specify --manifest when zero/multiple layout manifests exist')
        manifest=candidates[0]
    manifest=Path(manifest).resolve();data=json.loads(manifest.read_text(encoding='utf-8'))
    output.mkdir(parents=True,exist_ok=False);count=0
    for item in data['files']:
        source=Path(os.path.abspath(repository/(item.get('original_archive') or item['new_path'])))
        if not source.is_relative_to(repository) or not source.parent.resolve().is_relative_to(repository):raise RuntimeError('Unsafe source path')
        raw=os.readlink(source).encode('utf-8') if source.is_symlink() else source.read_bytes()
        if blob_oid(raw)!=item['old_oid']:raise RuntimeError('Original blob mismatch: '+item['old_path'])
        target=(output/item['old_path']).resolve()
        if not target.is_relative_to(output):raise RuntimeError('Unsafe output path')
        target.parent.mkdir(parents=True,exist_ok=True)
        if item['mode']=='120000':os.symlink(raw.decode('utf-8'),target)
        else:
            with target.open('xb') as f:f.write(raw)
            if item['mode']=='100755':target.chmod(0o755)
        count+=1
    receipt={'status':'completed','base_commit':data['base_commit'],'published_original_files':count,
        'original_blob_bytes_verified':True,'unpublished_runtime_assets_restored':False,'new_environment_steps':0}
    (output/'LEGACY_RESTORATION_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repository',required=True);p.add_argument('--output',required=True);p.add_argument('--manifest');a=p.parse_args()
    print(json.dumps(restore(a.repository,a.output,a.manifest)))
