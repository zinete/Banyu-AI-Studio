import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const report={segments:[],peak_mouth:0,errors:[]};
let currentId;
page.on('pageerror',e=>report.errors.push(String(e)));
page.on('websocket',socket=>socket.on('framereceived',frame=>{
 try{const event=JSON.parse(String(frame.payload));if(event.type==='play'&&event.id===currentId)report.segments.push({playback_id:event.playback_id,text:event.text,audio:event.audio});}catch{}
}));
const post=(path,body)=>page.evaluate(async({path,body})=>{const r=await fetch(path,{method:'POST',headers:{'X-Studio':'1','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const value=await r.json();if(!r.ok)throw Error(JSON.stringify(value));return value;},{path,body});
const state=()=>page.evaluate(async()=>await(await fetch('/api/state')).json());
async function waitForItem(id,deadline){
 while(Date.now()<deadline){
  const s=await state(),item=s.items.find(i=>i.id===id);
  const mouth=Number(await page.frameLocator('iframe').locator('canvas').getAttribute('data-mouth'));
  report.peak_mouth=Math.max(report.peak_mouth,mouth);
  if(item?.status==='done')return item;
  if(item&&['review','refused','cancelled'].includes(item.status))throw Error(`${item.status}: ${item.category}`);
  await page.waitForTimeout(500);
 }
 throw Error('Playback deadline exceeded');
}
try{
 await page.goto('http://127.0.0.1:8765');
 await page.frameLocator('iframe').getByRole('button',{name:'启用声音与角色'}).click();
 await page.waitForFunction(async()=>{const s=await(await fetch('/api/state')).json();return s.player_connected;});
 await post('/api/control/resume');
 const initial=await post('/api/messages',{nickname:'质量测试',text:'111'});
 const acknowledged=await waitForItem(initial.id,Date.now()+150000);
 report.numeric_reply=acknowledged.candidate;
 if(report.numeric_reply.trim()==='111')throw Error('Numeric echo regression');
 const submitted=await post('/api/messages',{nickname:'质量测试',text:'给我输出500字的故事'});
 currentId=submitted.id;
 const item=await waitForItem(currentId,Date.now()+420000);
 report.characters=item.candidate.length;
 report.answer=item.candidate;
 report.completed=item.status==='done';
 const ids=report.segments.map(s=>s.playback_id);
 if(report.characters<400||report.segments.length<2||new Set(ids).size!==ids.length||report.segments.map(s=>s.text).join('')!==item.candidate)throw Error('Long-answer segmentation regression');
 await post('/api/control/stop');await page.waitForTimeout(300);
 report.stopped_mouth=Number(await page.frameLocator('iframe').locator('canvas').getAttribute('data-mouth'));
 if(report.stopped_mouth!==0||report.peak_mouth<=.01||report.errors.length)throw Error('Mouth / stop regression');
 console.log(JSON.stringify({numeric_reply:report.numeric_reply,characters:report.characters,segments:report.segments.length,completed:report.completed,peak_mouth:report.peak_mouth,stopped_mouth:report.stopped_mouth,errors:report.errors},null,2));
}catch(e){report.failure=String(e);console.error(e);process.exitCode=1;}
finally{try{await post('/api/control/stop');}catch{}await browser.close();fs.writeFileSync('docs/verification/long-playback.json',JSON.stringify(report,null,2));}
