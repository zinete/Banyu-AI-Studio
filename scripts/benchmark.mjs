// Real browser + real local models. Run from repository root with server running.
// node scripts/benchmark.mjs --seconds 1800
import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import fs from 'node:fs';
const exec=promisify(execFile);
const secondsIndex=process.argv.indexOf('--seconds');
const duration=secondsIndex<0?1800:Number(process.argv[secondsIndex+1]);
if(!Number.isFinite(duration)||duration<1)throw Error('Invalid duration');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const outbound=[];await context.route('**/*',route=>{const url=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(url.hostname)){outbound.push(url.origin);return route.abort();}return route.continue();});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
fs.mkdirSync('docs/verification',{recursive:true});
const report={duration_requested:duration,started:new Date().toISOString(),gpu:[],items:[],fps:[],external_browser_requests:outbound,errors};
const post=(path,body)=>page.evaluate(async({path,body})=>{const r=await fetch(path,{method:'POST',headers:{'X-Studio':'1','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const value=await r.json();if(!r.ok)throw Error(JSON.stringify(value));return value;},{path,body});
const getState=()=>page.evaluate(async()=>await(await fetch('/api/state')).json());
try{
 await page.goto('http://127.0.0.1:8765');
 await page.frameLocator('iframe').getByRole('button',{name:'启用声音与角色'}).click({timeout:30000});
 await page.waitForFunction(async()=>{const r=await fetch('/api/state');return(await r.json()).player_connected;});
 const health=await page.evaluate(async()=>await(await fetch('/api/health')).json());
 if(health.llm!=='ready'||health.voice!=='ready')throw Error(`Not ready: ${JSON.stringify(health)}`);
 await post('/api/control/resume');
 const questions=['你好，用一句话介绍一下自己','聊聊你喜欢什么样的游戏','周末适合做些什么','推荐一种放松心情的方式','看电影时你会关注什么'];
 // One complete warm-up, excluded from latency statistics below.
 let warmup=true,index=0;
 const started=Date.now();
 while((Date.now()-started)/1000<duration){
  const {id}=await post('/api/messages',{nickname:'小麦',text:questions[index++%questions.length]});
  const deadline=Date.now()+180000;
  let item;
  while(Date.now()<deadline){
   await page.waitForTimeout(1000);
   const state=await getState();item=state.items.find(x=>x.id===id);
   try{const {stdout}=await exec('C:/Windows/System32/nvidia-smi.exe',['--query-gpu=name,memory.used,memory.total','--format=csv,noheader,nounits']);report.gpu.push({at:new Date().toISOString(),value:stdout.trim()});}catch{}
   if(state.stopped)throw Error('Unexpected paused state');
   if(item&&['done','review','refused','cancelled'].includes(item.status))break;
  }
  if(!item||!['done','review','refused','cancelled'].includes(item.status))throw Error('Message timed out');
  if(item.status!=='done')throw Error(`Normal dialogue did not play: ${item.category}`);
  report.items.push({id,status:item.status,category:item.category,latency:item.latency,warmup});warmup=false;
  const state=await getState();report.fps=state.metrics.filter(x=>x.fps!==undefined);
  fs.writeFileSync('docs/verification/benchmark-progress.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report.items.at(-1)));
  await page.waitForTimeout(1000);
 }
 report.elapsed=(Date.now()-started)/1000;
 const times=report.items.filter(x=>!x.warmup&&x.status==='done').map(x=>x.latency).sort((a,b)=>a-b);
 report.p95=times.length?times[Math.ceil(times.length*.95)-1]:null;
 report.minimum_fps=report.fps.length?Math.min(...report.fps.map(x=>x.fps)):null;
 report.complete=report.elapsed>=duration;
 await page.screenshot({path:'docs/verification/benchmark-final.png',fullPage:true});
}catch(e){report.failure=String(e);console.error(e);process.exitCode=1;}
finally{
 try{await post('/api/control/stop');}catch{}
 report.finished=new Date().toISOString();
 fs.writeFileSync('docs/verification/benchmark.json',JSON.stringify(report,null,2));
 await browser.close();
}
