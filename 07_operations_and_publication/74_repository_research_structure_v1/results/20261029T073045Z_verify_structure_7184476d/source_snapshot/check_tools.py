"""Small behavioral fixtures for relocation and exact-byte restoration, no environment."""
import ast,json,traceback
from pathlib import Path
import prepare
import restore_legacy_layout as legacy

def main():
    out=prepare.unique('tool_check');prepare.snapshot(out);checks=0
    def check(condition,message):
        nonlocal checks
        if not condition:raise AssertionError(message)
        checks+=1
    try:
        for file in prepare.HERE.glob('*.py'):
            ast.parse(file.read_text(encoding='utf-8'),filename=str(file));checks+=1
        mapping={'01_old':'group_a/01_old','02_old':'group_b/02_old'}
        valid={'01_old','02_old','01_old/README.md','02_old/report.md','02_old/clip.mp4','02_old/preview.gif','README.md'}
        raw=('\ufeff[report](../02_old/report.md?q=1#x)\r\n'
             '[![preview](../02_old/preview.gif)](../02_old/clip.mp4)\r\n'
             '[root](../README.md) [self](README.md) [missing](../02_old/missing.md)\r\n'
             '[absolute](https://github.com/rlatmddn0211/practice_allocation/blob/main/02_old/report.md#x)\r\n'
             '[fixed](https://github.com/rlatmddn0211/practice_allocation/blob/abc/02_old/report.md)\r\n'
             '`[code](../02_old/report.md)`\r\n'
             '```md\r\n[example](../02_old/report.md)\r\n```\r\n').encode()
        audit={'originally_valid':0,'valid_unchanged':0,'corrected_targets':0,'preexisting_missing':0,'missing_examples':[]}
        result,edits=prepare.rewrite_markdown(raw,'01_old/README.md','group_a/01_old/README.md',mapping,valid,audit)
        text=result.decode('utf-8')
        check('../../group_b/02_old/report.md?q=1#x' in text,'Sibling target/query/fragment')
        check('[![preview](../../group_b/02_old/preview.gif)](../../group_b/02_old/clip.mp4)' in text,'Nested GIF plus MP4')
        check('[root](../../README.md)' in text,'Root link')
        check('[self](README.md)' in text,'Same-version spelling')
        check('[missing](../02_old/missing.md)' in text,'Pre-existing missing link preserved')
        check('/blob/main/group_b/02_old/report.md#x' in text,'Same repository main absolute URL')
        check('/blob/abc/02_old/report.md' in text,'Fixed commit retained')
        check('`[code](../02_old/report.md)`' in text and '[example](../02_old/report.md)' in text,'Code examples retained')
        check(result.startswith(b'\xef\xbb\xbf') and result.count(b'\r\n')==raw.count(b'\r\n'),'BOM/line endings')
        check(audit['corrected_targets']==5 and len(edits)==5,'Correction count')
        extra=b'[repo](../) [spaced](../02_old/a%20b.md) [hash](../02_old/a%23b.md)\n````md\n```\n[code](../02_old/report.md)\n````\n'
        update,_=prepare.rewrite_markdown(extra,'01_old/README.md','group_a/01_old/README.md',mapping,
            valid|{'.','02_old/a b.md','02_old/a#b.md'},audit)
        check(b'[repo](../../)' in update,'Root-directory link')
        check(b'../../group_b/02_old/a%20b.md' in update and b'../../group_b/02_old/a%23b.md' in update,'Encoded paths retain meaning')
        check(b'[code](../02_old/report.md)' in update,'Four-character fenced block')
        repository=out/'fixture_repository';repository.mkdir()
        original=b'# Original\r\n[old](../02_old/report.md)\r\n'
        (repository/'original.bin').write_bytes(original)
        (repository/'code.py').write_bytes(b'print(1)\n')
        manifest=out/'fixture_manifest.json'
        prepare.save(manifest,{'base_commit':'fixture','files':[
            {'old_path':'01_old/README.md','new_path':'unused.md','original_archive':'original.bin','old_oid':prepare.oid(original),'mode':'100644'},
            {'old_path':'02_old/code.py','new_path':'code.py','old_oid':prepare.oid(b'print(1)\n'),'mode':'100644'}]})
        receipt=legacy.restore(repository,out/'restored_fixture',manifest)
        check(receipt['published_original_files']==2,'Restore count')
        check((out/'restored_fixture'/'01_old'/'README.md').read_bytes()==original,'Restore exact original document')
        check((out/'restored_fixture'/'02_old'/'code.py').read_bytes()==b'print(1)\n','Restore exact code')
        rejected=False
        try:legacy.restore(repository,out/'restored_fixture',manifest)
        except RuntimeError:rejected=True
        check(rejected,'Existing output overwrite rejected')
        prepare.save(out/'verification.json',{'passed':True,'checks':checks,'new_environment_steps':0,
            'scope':'Behavioral fixtures only; no scientific evaluation'})
        print(json.dumps({'tool_check_dir':str(out),'passed':True,'checks':checks}))
    except BaseException:
        prepare.save(out/'FAILED.json',{'traceback':traceback.format_exc(),'new_environment_steps':0});raise

if __name__=='__main__':main()
