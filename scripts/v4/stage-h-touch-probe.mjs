#!/usr/bin/env node
/** What element does a touch actually land on, and what touch-action applies there? */
import { spawn } from "node:child_process";
import { chromium } from "playwright";
const REPO="/Users/xiaoli/Downloads/mirrorweb", port=5361;
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const child=spawn("npx",["vite","preview","--host","127.0.0.1","--port",String(port),"--strictPort"],{cwd:REPO,stdio:["ignore","pipe","pipe"]});
await new Promise((res,rej)=>{const t=setTimeout(()=>rej(new Error("no preview")),30000);const on=(c)=>{if(String(c).includes("Local:")){clearTimeout(t);res();}};child.stdout.on("data",on);child.stderr.on("data",on);});
const browser=await chromium.launch({channel:"chrome",headless:process.env.ILG_CAPTURE_HEADLESS==="1",args:["--enable-unsafe-webgpu","--enable-webgpu-developer-features"]});
const ctx=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:3,isMobile:true,hasTouch:true});
const page=await ctx.newPage();
await page.goto(`http://127.0.0.1:${port}/?optics=v4&qa=1`,{waitUntil:"load"});
await page.waitForFunction(()=>window.__ILG_QA__?.getState()?.ready===true,undefined,{timeout:90000});
await sleep(1500);
console.log(JSON.stringify(await page.evaluate(()=>{
  const el=document.elementFromPoint(312,633);
  const chain=[]; let n=el;
  while(n && n!==document.documentElement.parentNode){
    chain.push({tag:n.tagName?.toLowerCase(), id:n.id||null, touchAction:getComputedStyle(n).touchAction, overscroll:getComputedStyle(n).overscrollBehavior, pe:getComputedStyle(n).pointerEvents});
    n=n.parentElement;
  }
  return {hit:{tag:el?.tagName?.toLowerCase(), id:el?.id||null, cls:el?.className||null}, chain};
}),null,2));
await browser.close(); child.kill("SIGTERM");
