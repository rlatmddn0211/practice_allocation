// Bounded read-only browser verification of the authored report, using local Chrome CDP.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const self = fileURLToPath(import.meta.url);
const root = path.dirname(self);
const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0,15) + 'Z';
const output = path.join(root, 'results', `${stamp}_report_browser_${crypto.randomUUID().slice(0,8)}`);
fs.mkdirSync(output, { recursive: false });
fs.mkdirSync(path.join(output, 'source_snapshot'));
fs.copyFileSync(self, path.join(output, 'source_snapshot', 'verify_report.mjs'));
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const profile = path.join(output, 'browser_profile');
const url = 'http://127.0.0.1:8707/';
const record = { started_at: new Date().toISOString(), status: 'running', url,
  script_sha256: sha(self), built_html_sha256: sha(path.join(root,'report_app/dist/index.html')),
  node: process.version, checks: [], screenshots: [], exceptions: [] };
let chrome, socket, call;
function check(name, pass, details) {
  record.checks.push({ name, passed: Boolean(pass), details });
  if (!pass) throw new Error(name);
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  const log = fs.openSync(path.join(output, 'browser.log'), 'a');
  chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
    { windowsHide:true, stdio:['ignore',log,log] });
  chrome.on('error', e => { record.launch_error = String(e); });
  const portFile = path.join(profile, 'DevToolsActivePort');
  for (let i=0; i<100 && !fs.existsSync(portFile); i++) await pause(100);
  check('browser_started', fs.existsSync(portFile), record.launch_error);
  const port = fs.readFileSync(portFile,'utf8').split('\n')[0];
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {method:'PUT'})).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { socket.addEventListener('open', resolve, {once:true}); socket.addEventListener('error',reject,{once:true}); });
  let serial=0; const pending=new Map();
  socket.addEventListener('message', ({data}) => {
    const msg=JSON.parse(String(data));
    if(msg.id && pending.has(msg.id)) { const p=pending.get(msg.id); pending.delete(msg.id); clearTimeout(p.timer); msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); }
    if(msg.method==='Runtime.exceptionThrown') record.exceptions.push(msg.params.exceptionDetails);
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{ const id=++serial; const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`Timeout ${method}`));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression => {
    const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await call('Runtime.enable'); await call('Page.enable');
  for(let i=0;i<100;i++) { if(await evaluate('Boolean(document.querySelector(".replication-report"))')) break; await pause(100); }
  check('report_rendered',await evaluate('Boolean(document.querySelector(".replication-report"))'));
  const ids=['replication-summary','primary-results','baseline-context','replication-effect','outlier-context','drawer-finding','drawer-contrast','recovery-finding','window-recovery','task-finding','task-contributions','task-detail','budget-finding','budget-table','combined-context','cohort-comparison','scope-next','execution-methods'];
  const componentExpression = `Array.from(document.querySelectorAll('[data-component-id]')).map(e=>({id:e.getAttribute('data-component-id'),text:e.innerText}))`;
  const components=await evaluate(componentExpression);
  record.components=components.map(x=>({id:x.id,characters:x.text.length}));
  check('all_authored_components',ids.every(id=>components.some(c=>c.id===id)),record.components);
  const body=await evaluate('document.body.innerText');
  check('key_values_visible', ['55.33','55.00','49.33','+6.00','+6.33','1,127/1,127'].every(x=>body.includes(x)));
  check('no_template_or_unicode_damage',!body.includes('Product adoption') && !body.includes('Synthetic example') && !body.includes('\uFFFD'));
  check('no_unrendered_markdown_markers', !body.includes('**'));
  for(const [name,width,height] of [['desktop',1280,1000],['narrow',420,1000]]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await pause(450);
    const geometry=await evaluate(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,chart:Array.from(document.querySelectorAll('.recharts-bar-rectangle')).map(e=>{const b=e.getBoundingClientRect();return {width:b.width,height:b.height}}),tables:document.querySelectorAll('.replication-report table').length})`);
    check(`${name}_page_no_overflow`,geometry.scroll<=geometry.width+2,geometry);
    check(`${name}_bars_painted`,geometry.chart.filter(x=>x.width>0 && x.height>0).length===12,geometry.chart);
    check(`${name}_seven_tables`,geometry.tables===7,geometry.tables);
    const metrics=await call('Page.getLayoutMetrics');
    const total=Math.ceil(metrics.cssContentSize.height);
    // Full authored content is preserved in bounded-height tiles for visual review.
    for(let y=0,part=0;y<total;y+=1400,part++) {
      const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y,width,height:Math.min(1400,total-y),scale:1}});
      const filename=`${name}_${String(part).padStart(2,'0')}.png`;
      fs.writeFileSync(path.join(output,filename),Buffer.from(shot.data,'base64'));
      record.screenshots.push({file:filename,width,y,height:Math.min(1400,total-y)});
    }
  }
  await evaluate(`(()=>{const s=document.querySelector('select[aria-label="과제별 결과의 후속 seed"]');s.value='1905';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await pause(100);
  const selected=await evaluate(`document.querySelector('[data-component-id="task-detail"]').innerText`);
  check('seed_filter_1905',selected.includes('52.00') && selected.includes('44.00') && selected.includes('22.00'),selected);
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.innerText==='평균으로 초기화').click()`);
  await pause(100);
  const reset=await evaluate(`({seed:document.querySelector('select[aria-label="과제별 결과의 후속 seed"]').value,text:document.querySelector('[data-component-id="task-detail"]').innerText})`);
  check('seed_filter_reset',reset.seed==='all' && reset.text.includes('49.33') && reset.text.includes('55.00'),reset);
  check('no_uncaught_browser_exceptions',record.exceptions.length===0,record.exceptions);
  check('source_script_unchanged',record.script_sha256===sha(self));
  record.status='passed';
} catch(error) { record.status='failed';record.error=String(error.stack||error);process.exitCode=1; }
finally {
  record.completed_at=new Date().toISOString();
  if(call) { try { await call('Browser.close'); } catch {} }
  socket?.close();
  if(chrome && !call) chrome.kill();
  fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(record,null,2)+'\n');
  console.log(JSON.stringify({status:record.status,output,checks:record.checks.length,screenshots:record.screenshots.length,error:record.error}));
}
