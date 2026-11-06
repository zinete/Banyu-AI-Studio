import {chromePath} from './browser-runtime.mjs';
import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';
const browser=await chromium.launch({executablePath:chromePath(),headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const report={peak_mouth:0,errors:[]};
page.on('pageerror',e=>report.errors.push(String(e)));
const post=(path,body)=>page.evaluate(async({path,body})=>{const r=await fetch(path,{method:'POST',headers:{'X-Studio':'1','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;},{path,body});
try{
 await page.goto('http://127.0.0.1:8765');
 const display=page.frameLocator('iframe');
 await display.getByRole('button',{name:'启用声音与角色'}).click();
 await page.waitForFunction(async()=>{const s=await(await fetch('/api/state')).json();return s.player_connected;});
 await post('/api/control/resume');
 const {id}=await post('/api/messages',{nickname:'造型测试',text:'你好，请用一句话介绍一下你自己。'});
 const deadline=Date.now()+120000;
 while(Date.now()<deadline){
  const level=Number(await display.locator('canvas').getAttribute('data-mouth'));
  if(level>report.peak_mouth){report.peak_mouth=level;}
  if(level>.12&&!report.speaking_screenshot){await display.locator('.display').screenshot({path:'docs/screenshots/yier-bubu-speaking.png'});report.speaking_screenshot=true;}
  const item=await page.evaluate(async id=>{const s=await(await fetch('/api/state')).json();return s.items.find(i=>i.id===id);},id);
  if(item?.status==='done'){report.answer=item.candidate;report.playback_completed=true;break;}
  if(item&&['review','refused','cancelled'].includes(item.status))throw Error(`${item.status}: ${item.category}`);
  await page.waitForTimeout(250);
 }
 await post('/api/control/stop');await page.waitForTimeout(300);
 report.stopped_mouth=Number(await display.locator('canvas').getAttribute('data-mouth'));
 report.stopped_action=await display.locator('canvas').getAttribute('data-action');
 await display.locator('.display').screenshot({path:'docs/screenshots/yier-bubu-stage.png'});
 if(!report.playback_completed||report.peak_mouth<=.01||report.stopped_mouth!==0||report.stopped_action!=='idle'||report.errors.length)throw Error('Avatar playback regression');
 console.log(JSON.stringify(report,null,2));
}catch(e){report.failure=String(e);console.error(e);process.exitCode=1;}
finally{try{await post('/api/control/stop');}catch{}await browser.close();fs.writeFileSync('docs/verification/bear-playback.json',JSON.stringify(report,null,2));}
