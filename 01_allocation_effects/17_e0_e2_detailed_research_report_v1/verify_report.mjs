// Read-only verification of this report with an isolated, headless Chrome profile.
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
const record={started_at:new Date().toISOString(),url:'http://127.0.0.1:8717/',node:process.version,status:'running',checks:[],exceptions:[],screenshots:[],
  source_sha256:sha(self),build:JSON.parse(fs.readFileSync(path.join(root,'report_app/dist/data-app-build.json'),'utf8'))};
let browser, socket, call;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function check(name,value,details){record.checks.push({name,passed:Boolean(value),details});if(!value)throw new Error(name);}
try {
  const log=fs.openSync(path.join(output,'browser.log'),'a'), profile=path.join(output,'profile');
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
  for(let i=0;i<100;i++){if(await evaluate('Boolean(document.querySelector(".research-report"))'))break;await sleep(100);}
  check('report_mounted',await evaluate('Boolean(document.querySelector(".research-report"))'));
  const ids=['main-finding','primary-table','design','e0-finding','e0-results','baseline-finding','baseline-table','e1-primary-finding','e1-mean-seeds','context-finding','context-table','task-finding','task-tradeoffs','task-absolute-table','budget-finding','budget-chart','selector-finding','rules-table','e2-finding','e2-absolute-table','e2-seed-chart','research-judgment','uncertainty','cost-table'];
  const components=await evaluate(`Array.from(document.querySelectorAll('[data-component-id]')).map(e=>({id:e.getAttribute('data-component-id'),text:e.innerText}))`);
  check('all_24_authored_components',ids.every(id=>components.some(c=>c.id===id)),components.map(c=>({id:c.id,characters:c.text.length})));
  const body=await evaluate('document.body.innerText');
  fs.writeFileSync(path.join(output,'rendered_text.txt'),body);
  check('no_fixture_or_encoding_markers',!body.includes('Synthetic')&&!body.includes('\uFFFD')&&!body.includes('**'),
    {fixture:body.includes('Synthetic'),replacement:body.includes('\uFFFD'),raw_markdown:body.match(/.{0,50}\*\*.{0,90}/g)});
  for(const [id,values] of [['e0-results',['57.33','49.42','+7.92']],['e1-mean-seeds',['66.90','+0.39','−1.92'.replace('−','-')]],['e2-absolute-table',['4.11','4.89','65.08']],['rules-table',['-3.88','+3.57']]]){
    const t=components.find(c=>c.id===id)?.text||'';check(id+'_values',values.every(v=>t.includes(v)),t);
  }
  for(const [name,width,height] of [['desktop',1360,1000],['narrow',420,1000]]){
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(650);
    const geo=await evaluate(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,charts:Array.from(document.querySelectorAll('[data-component-kind="chart"]')).map(e=>({id:e.dataset.componentId,bars:Array.from(e.querySelectorAll('.recharts-bar-rectangle')).map(n=>{const b=n.getBoundingClientRect();return {w:b.width,h:b.height};})}))})`);
    check(name+'_no_horizontal_page_overflow',geo.scroll<=geo.width+2,geo);
    check(name+'_three_visible_charts',geo.charts.length===3&&geo.charts.every(c=>c.bars.some(b=>b.w>0&&b.h>0)),geo.charts);
    for(const id of ['main-finding','e0-results','baseline-table','e1-mean-seeds','context-table','task-tradeoffs','task-absolute-table','budget-chart','rules-table','e2-absolute-table','e2-seed-chart','cost-table']){
      const box=await evaluate(`(()=>{const e=document.querySelector('[data-component-id="${id}"]');e.scrollIntoView({block:'start'});window.scrollBy(0,-96);const b=e.getBoundingClientRect();return {x:Math.max(0,b.x),y:Math.max(0,b.y+scrollY),width:Math.min(b.width,innerWidth-Math.max(0,b.x)),height:b.height};})()`);
      const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{...box,scale:1}});
      const filename=`${name}_${id}.png`;fs.writeFileSync(path.join(output,filename),Buffer.from(screenshot.data,'base64'));record.screenshots.push(filename);
    }
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1360,height:1000,deviceScaleFactor:1,mobile:false});
  for(const [label,count,include] of [['200k',3,'65.17'],['400k',3,'67.25'],['전체',6,'65.17']]){
    await evaluate(`Array.from(document.querySelectorAll('[aria-label="출발 checkpoint 선택"] button')).find(b=>b.innerText==='${label}').click()`);await sleep(120);
    const state=await evaluate(`(()=>{const e=document.querySelector('[data-component-id="context-table"]');return {rows:e.querySelectorAll('tbody tr').length,text:e.innerText};})()`);
    check('checkpoint_filter_'+label,state.rows===count&&state.text.includes(include),state);
  }
  // All authored rows and definitions are served from the same reviewed snapshot.
  const manifest=record.build;
  const snapshotFiles=fs.readdirSync(path.join(root,'report_app/dist')).filter(n=>/^snapshot\..*\.json$/.test(n));
  check('one_current_snapshot',snapshotFiles.length===1,snapshotFiles);
  const response=await fetch(record.url+snapshotFiles[0]);const data=await response.json();
  check('served_snapshot_has_18_queries',Object.keys(data.queries).length===18,Object.keys(data.queries));
  record.build_status=data.buildStatus;
  check('no_uncaught_browser_errors',record.exceptions.length===0,record.exceptions);
  record.status='passed';
} catch(e){record.status='failed';record.error=String(e.stack||e);process.exitCode=1;}
finally {
  if(call){try{await call('Browser.close');}catch{}}
  socket?.close();if(browser&&!call)browser.kill();
  record.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(record,null,2)+'\n');
  console.log(JSON.stringify({status:record.status,output,checks:record.checks.length,screenshots:record.screenshots.length,error:record.error}));
}
