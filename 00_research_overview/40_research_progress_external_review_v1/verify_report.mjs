// Bounded read-only inspection using a new isolated headless browser profile.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const self=fileURLToPath(import.meta.url), root=path.dirname(self);
const output=path.join(root,'results',new Date().toISOString().replace(/[-:]/g,'').slice(0,15)+'Z_browser_'+crypto.randomUUID().slice(0,8));
fs.mkdirSync(output,{recursive:false});
fs.copyFileSync(self,path.join(output,'verify_source.mjs'));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const record={started_at:new Date().toISOString(),url:'http://127.0.0.1:8740/',node:process.version,status:'running',checks:[],exceptions:[],screenshots:[],
  source_sha256:sha(self),report_sha256:sha(path.join(root,'research_progress_report_ko.md')),
  build:JSON.parse(fs.readFileSync(path.join(root,'report_app/dist/data-app-build.json'),'utf8')),
  environment_steps:0,persistent_updates:0,clone_updates:0};
let browser,socket,call;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function check(name,value,details){record.checks.push({name,passed:Boolean(value),details});if(!value)throw new Error(name);}
try {
  const log=fs.openSync(path.join(output,'browser.log'),'a'),profile=path.join(output,'profile');
  browser=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
    {windowsHide:true,stdio:['ignore',log,log]});
  browser.on('error',e=>{record.launch_error=String(e);});
  const portFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<100&&!fs.existsSync(portFile);i++)await sleep(100);
  check('browser_started',fs.existsSync(portFile),record.launch_error);
  const port=fs.readFileSync(portFile,'utf8').split('\n')[0];
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(record.url)}`,{method:'PUT'})).json();
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true});});
  let seq=0;const pending=new Map();
  socket.addEventListener('message',({data})=>{
    const m=JSON.parse(String(data));
    if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}
    if(m.method==='Runtime.exceptionThrown')record.exceptions.push(m.params.exceptionDetails);
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(Error(method+' timeout'));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await call('Runtime.enable');await call('Page.enable');
  for(let i=0;i<100;i++){if(await evaluate('Boolean(document.querySelector(".research-progress"))'))break;await sleep(100);}
  check('report_mounted',await evaluate('Boolean(document.querySelector(".research-progress"))'));
  const parts=await evaluate(`Array.from(document.querySelectorAll('.research-section-anchor')).map(e=>({id:e.id,text:e.innerText}))`);
  check('all_17_sections_rendered',parts.length===17,parts.map(x=>({id:x.id,characters:x.text.length})));
  for(let n=1;n<=17;n++)check('section_'+n,parts.some(x=>x.id==='read-section-'+String(n).padStart(2,'0')&&x.text.length>250));
  const body=await evaluate('document.body.innerText');
  fs.writeFileSync(path.join(output,'rendered_text.txt'),body);
  check('no_fixture_or_encoding_markers',!body.includes('Synthetic')&&!body.includes('\uFFFD')&&!body.includes('Active accounts'));
  const reportText=fs.readFileSync(path.join(root,'research_progress_report_ko.md'),'utf8');
  const expectedTables=reportText.split('\n').filter(line=>/^\|(?:\s*:?---+:?\s*\|)+\s*$/.test(line)).length;
  const renderedTables=await evaluate('document.querySelectorAll(".research-section-anchor [data-logical-table]").length');
  check('all_markdown_tables_rendered',renderedTables===expectedTables,{expected:expectedTables,actual:renderedTables});
  const expectedRows=reportText.split('\n').filter(line=>line.startsWith('|')).length-expectedTables*2;
  check('all_table_rows_visible',await evaluate('document.querySelectorAll(".research-section-anchor tbody tr").length')===expectedRows,expectedRows);
  for(const [n,values] of [[7,['+7.92','+0.39','-0.78']],[10,['-0.074','-0.296','+0.704','98.57']],[11,['36.58','30.75','3.42','19개']],[12,['14,960,000','78,276,809','93,236,809']],[15,['9.28M','실행·예약하지 않았고']]]) {
    const text=parts.find(x=>x.id==='read-section-'+String(n).padStart(2,'0')).text;
    check('key_values_'+n,values.every(v=>text.includes(v)));
  }
  for(const [name,width,height] of [['desktop',1360,1000],['narrow',420,1000]]){
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(300);
    const geo=await evaluate(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,tables:Array.from(document.querySelectorAll('.research-section-anchor table')).map(t=>({width:t.getBoundingClientRect().width,scroll:t.scrollWidth,client:t.clientWidth,rows:t.rows.length}))})`);
    check(name+'_no_page_overflow',geo.scroll<=geo.width+2,geo);
    check(name+'_tables_present',geo.tables.every(t=>t.width>0&&t.rows>1));
    for(const n of (name==='desktop'?[1,10,11,12,15]:[1,11])){
      await evaluate(`(()=>{const e=document.getElementById('read-section-${String(n).padStart(2,'0')}');e.scrollIntoView({block:'start'});window.scrollBy(0,-100);})()`);
      const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      const filename=`${name}_section_${n}.png`;fs.writeFileSync(path.join(output,filename),Buffer.from(screenshot.data,'base64'));record.screenshots.push(filename);
    }
  }
  await evaluate(`document.querySelector('.research-contents details').open=true`);
  check('toc_targets_exist',await evaluate(`Array.from(document.querySelectorAll('.research-contents a')).every(a=>document.querySelector(a.getAttribute('href')))`));
  const snapshotFiles=fs.readdirSync(path.join(root,'report_app/dist')).filter(n=>/^snapshot\..*\.json$/.test(n));
  check('one_current_snapshot',snapshotFiles.length===1,snapshotFiles);
  const data=await(await fetch(record.url+snapshotFiles[0])).json();
  check('served_snapshot_complete',data.report.sections.length===17&&data.buildStatus==='complete'&&data.report.asOf==='2026-10-19');
  check('source_scopes',data.report.sections.every(s=>s.queryIds.every(q=>data.queries[q]?.source.metricDefinitions.every(d=>d.componentIds.includes(s.id)))));
  check('no_uncaught_browser_errors',record.exceptions.length===0,record.exceptions);
  record.status='passed';
}catch(e){record.status='failed';record.error=String(e.stack||e);process.exitCode=1;}
finally{
  if(call){try{await call('Browser.close');}catch{}}
  socket?.close();if(browser&&!call)browser.kill();
  record.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(record,null,2)+'\n');
  console.log(JSON.stringify({status:record.status,output,checks:record.checks.length,screenshots:record.screenshots.length,error:record.error}));
}
