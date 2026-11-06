import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';
const config=JSON.parse(fs.readFileSync('.runtime/lan.json','utf8'));
const base=`http://${config.host}:8765`;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const context=await browser.newContext();
const page=await context.newPage();
const errors=[];page.on('pageerror',error=>errors.push(String(error)));
try{
 const anonymous=await context.request.get(`${base}/api/session`);
 if(anonymous.status()!==403)throw Error('Anonymous session endpoint must be blocked');
 await page.goto(`${base}/?access=${encodeURIComponent(config.access_token)}`);
 await page.waitForFunction(()=>document.querySelector('.topbar .signal')?.textContent==='本地连接');
 await page.frameLocator('iframe').getByRole('button',{name:'启用声音与角色'}).waitFor();
 const health=await page.evaluate(async()=>await(await fetch('/api/health')).json());
 const state=await page.evaluate(async()=>{const r=await fetch('/api/state');return r.status;});
 const audioContext=await page.evaluate(()=>typeof window.AudioContext);
 if(state!==200||!health.lan_enabled||audioContext!=='function'||page.url()!==`${base}/`||errors.length)throw Error('LAN browser verification failed');
 const result={anonymous_blocked:true,token_removed_from_url:true,authenticated_state:state,lan_websocket:true,audio_context:audioContext,health,errors};
 fs.writeFileSync('docs/verification/lan.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
