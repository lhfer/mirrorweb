#!/usr/bin/env node
/**
 * Isolates why touch dragging barely moves the grid.
 *
 * Runs the same CDP touch path twice: once against the page as shipped, and
 * once with `touch-action: none` injected from the harness. Nothing is written
 * to product code; the injection exists only to identify the cause.
 */
import { spawn } from "node:child_process";
import { chromium } from "playwright";
const port=5326, REPO="/Users/xiaoli/Downloads/mirrorweb";
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const child=spawn("npx",["vite","preview","--host","127.0.0.1","--port",String(port),"--strictPort"],{cwd:REPO,stdio:["ignore","pipe","pipe"]});
await new Promise((res,rej)=>{const t=setTimeout(()=>rej(new Error("no preview")),30000);const on=(c)=>{if(String(c).includes("Local:")){clearTimeout(t);res();}};child.stdout.on("data",on);child.stderr.on("data",on);});
const browser=await chromium.launch({channel:"chrome",headless:process.env.ILG_CAPTURE_HEADLESS==="1",args:["--enable-unsafe-webgpu","--enable-webgpu-developer-features"]});
async function run(injectTouchAction){
  const ctx=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:3,isMobile:true,hasTouch:true});
  const page=await ctx.newPage(); const cdp=await ctx.newCDPSession(page);
  await page.goto(`http://127.0.0.1:${port}/?optics=v4&qa=1`,{waitUntil:"load"});
  await page.waitForFunction(()=>window.__ILG_QA__?.getState()?.ready===true,undefined,{timeout:90000});
  if(injectTouchAction) await page.addStyleTag({content:"html,body,canvas{touch-action:none !important;overscroll-behavior:none;}"});
  await page.evaluate(()=>{window.E={pointermove:0,pointerup:0,touchmove:0};
    window.addEventListener("pointermove",()=>window.E.pointermove++,true);
    window.addEventListener("pointerup",()=>window.E.pointerup++,true);
    window.addEventListener("touchmove",()=>window.E.touchmove++,true);});
  await page.evaluate(()=>window.__ILG_QA__.reset()); await sleep(1200);
  const b=await page.evaluate(()=>window.__ILG_QA__.getState());
  await cdp.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x:312,y:633,id:1}]});
  for(let k=1;k<=16;k++){await cdp.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[{x:312-k*15,y:633-k*17,id:1}]});await sleep(28);}
  await cdp.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});
  await sleep(2400);
  const a=await page.evaluate(()=>window.__ILG_QA__.getState());
  const e=await page.evaluate(()=>window.E);
  await ctx.close();
  return {events:e, movedPx:Math.round(Math.hypot(a.scrollX-b.scrollX,a.scrollY-b.scrollY))};
}
console.log("as shipped        :", JSON.stringify(await run(false)));
console.log("+touch-action:none:", JSON.stringify(await run(true)));
await browser.close(); child.kill("SIGTERM");
