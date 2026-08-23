#!/usr/bin/env node
/**
 * Visual Convergence Sprint 2 -- structural reconnaissance of BOTH pages.
 *
 * One reader, two sides. It answers the two questions the matched-content
 * harness cannot be written without:
 *
 *   1. Where does a card's copy actually live? (which leaf elements carry the
 *      ILG code / category / meta / title / deck, in document order) -- the
 *      copy injector rewrites those leaves and nothing else.
 *   2. What is in the page chrome? Every element of the footer subtree with
 *      its rect, its computed type, and -- for the wordmark -- whether it is
 *      an <img> or type. Plus any full-width gradient scrim above it.
 *
 * Nothing here judges anything. It records structure so the harness and the
 * P0 decision are written against what the pages contain rather than against
 * a memory of them.
 *
 * Usage: vc2-recon.mjs [--out=<json>] [--vps=WxH,...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";
const LOCAL = "http://127.0.0.1:5293/?review=target&qa";
const MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
  + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

const opts = { out: path.join(REPO, "artifacts/visual-convergence/recon.json"),
               vps: ["1440x900", "390x844"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}

/** Runs in-page on BOTH sides. Pure structure, no side-specific branches. */
function readStructure() {
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return [+r.x.toFixed(2), +r.y.toFixed(2), +r.width.toFixed(2), +r.height.toFixed(2)];
  };
  const style = (el) => {
    const cs = getComputedStyle(el);
    return {
      font: `${cs.fontWeight} ${cs.fontSize}/${cs.lineHeight} ${cs.fontFamily}`,
      letterSpacing: cs.letterSpacing, textTransform: cs.textTransform,
      color: cs.color, opacity: cs.opacity,
      background: cs.backgroundImage !== "none" ? cs.backgroundImage.slice(0, 160)
                                                : cs.backgroundColor,
      border: cs.borderTopWidth === "0px" ? null
        : `${cs.borderTopWidth} ${cs.borderTopColor} r=${cs.borderTopLeftRadius}`,
      filter: cs.filter === "none" ? null : cs.filter,
      backdrop: cs.backdropFilter && cs.backdropFilter !== "none" ? cs.backdropFilter : null,
      display: cs.display, flexDirection: cs.flexDirection, alignItems: cs.alignItems,
      justifyContent: cs.justifyContent, gap: cs.gap,
      position: cs.position, zIndex: cs.zIndex,
    };
  };
  const outline = (root, depth = 0, acc = []) => {
    for (const el of root.children) {
      const ownText = [...el.childNodes]
        .filter((n) => n.nodeType === 3).map((n) => n.textContent.trim())
        .filter(Boolean).join(" ");
      acc.push({
        depth, tag: el.tagName.toLowerCase(),
        cls: String(el.className).slice(0, 150) || null,
        ownText: ownText || null,
        allText: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120) || null,
        rect: rect(el),
        ...(el.tagName === "IMG"
          ? { img: { src: String(el.currentSrc || el.src).slice(-90),
                     natural: [el.naturalWidth, el.naturalHeight] } }
          : {}),
        style: style(el),
      });
      outline(el, depth + 1, acc);
    }
    return acc;
  };

  /* ---- cards: every element with a matrix3d transform and one ILG code ---- */
  const cards = [];
  for (const d of document.querySelectorAll("div")) {
    if (!d.style.transform || !d.style.transform.includes("matrix3d")) continue;
    const text = (d.textContent || "").replace(/\s+/g, " ").trim();
    const codes = text.match(/ILG[—-]\s?(\d+)/g) || [];
    if (codes.length !== 1) continue;
    cards.push({ el: d, code: Number(text.match(/ILG[—-]\s?(\d+)/)[1]),
                 hidden: d.style.visibility === "hidden" });
  }
  cards.sort((a, b) => a.code - b.code);
  const visible = cards.find((c) => !c.hidden) ?? cards[0];

  /* ---- the copy leaves of one card, in document order ---- */
  const leaves = [];
  if (visible) {
    const walk = (el, pathStr) => {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3)
        .map((n) => n.textContent).join("").trim();
      if (own) {
        leaves.push({ path: pathStr, tag: el.tagName.toLowerCase(),
                      cls: String(el.className).slice(0, 90) || null, text: own,
                      rect: rect(el), style: style(el) });
      }
      [...el.children].forEach((k, i) => walk(k, `${pathStr}/${k.tagName.toLowerCase()}[${i}]`));
    };
    walk(visible.el, "card");
  }

  /* ---- page chrome: the footer subtree, plus any full-width scrim ---- */
  const chromeRoots = [];
  const seen = new Set();
  for (const el of document.querySelectorAll("footer, [class*='bottom-0'], .page-footer")) {
    let top = el;
    while (top.parentElement && top.parentElement !== document.body
           && (top.parentElement.className || "").includes("bottom")) top = top.parentElement;
    if (seen.has(top)) continue;
    seen.add(top);
    chromeRoots.push({ tag: top.tagName.toLowerCase(),
                       cls: String(top.className).slice(0, 150) || null,
                       rect: rect(top), style: style(top), tree: outline(top) });
  }
  // Anything painting a gradient across the full page width, wherever it lives.
  const scrims = [];
  for (const el of document.body.querySelectorAll("*")) {
    const cs = getComputedStyle(el);
    if (!cs.backgroundImage.includes("gradient")) continue;
    const r = el.getBoundingClientRect();
    if (r.width < innerWidth * 0.9 || r.height < 24) continue;
    scrims.push({ tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 150) || null,
                  rect: rect(el), background: cs.backgroundImage.slice(0, 200),
                  opacity: cs.opacity, zIndex: cs.zIndex, position: cs.position });
  }

  return {
    viewport: [innerWidth, innerHeight], dpr: devicePixelRatio,
    cardCount: cards.length, visibleCards: cards.filter((c) => !c.hidden).length,
    codes: cards.map((c) => c.code),
    sampledCard: visible ? { code: visible.code, rect: rect(visible.el), leaves } : null,
    chromeRoots, scrims,
    css3dRoots: [...document.querySelectorAll("div")]
      .filter((d) => d.style.transform && d.style.transform.includes("perspective("))
      .map((d) => ({ cls: String(d.className).slice(0, 90) || null,
                     parentCls: String(d.parentElement?.className || "").slice(0, 90) || null,
                     transform: d.style.transform.slice(0, 90) })),
  };
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const out = { what: "VC2 structural recon of both pages", startedAt: new Date().toISOString(),
              target: TARGET, local: LOCAL, sides: {} };

for (const [side, url] of [["target", TARGET], ["local", LOCAL]]) {
  out.sides[side] = {};
  for (const vp of opts.vps) {
    const [w, h] = vp.split("x").map(Number);
    const touch = w < 768;
    const ctx = await browser.newContext({ viewport: { width: w, height: h },
      deviceScaleFactor: 1, hasTouch: touch, isMobile: touch,
      ...(touch ? { userAgent: MOBILE_UA } : {}) });
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: "load", timeout: 120000 });
    if (side === "local") {
      await page.waitForFunction(() => window.__ILG_QA__?.getAssetState?.()?.ready === true,
        undefined, { timeout: 180000 }).catch(() => {});
    }
    await page.waitForTimeout(side === "target" ? 9000 : 5000);
    out.sides[side][vp] = await page.evaluate(readStructure);
    await ctx.close();
    console.log(`${side} ${vp}: cards=${out.sides[side][vp].cardCount} `
      + `chrome=${out.sides[side][vp].chromeRoots.length} scrims=${out.sides[side][vp].scrims.length}`);
  }
}
await browser.close();
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(out, null, 1));
console.log(`-> ${opts.out}`);
