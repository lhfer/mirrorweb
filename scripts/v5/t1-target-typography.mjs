#!/usr/bin/env node
/**
 * Read the Target's TYPOGRAPHY, in numbers, from its own DOM.
 *
 * The Target draws its card text with a CSS3D layer, so every type decision is
 * a computed style on a real element: family, weight, size, line-height,
 * tracking, the container's box, its padding, its overflow and clip, the depth
 * relationship between the text plane and the card plane, and the DOM order
 * that decides which label paints over which. None of that has to be guessed
 * from pixels, and none of it should be.
 *
 * Read-only. It loads the public page, waits for it to settle and reads
 * computed style. It never interacts, never posts, and stores no Target pixels
 * unless --shots is given (and then only under artifacts/, which is ignored).
 *
 * Usage: t1-target-typography.mjs --out=<dir> --vps=WxH,... [--shots]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";
const opts = { url: TARGET, local: false, out: path.join(REPO, "artifacts/t1/target-typography"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"],
  shots: false, settle: 6000 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a === "--shots") opts.shots = true;
  // The same reader, pointed at our own page. One instrument for both sides:
  // a contract compared with a differently-written reader would be comparing
  // two readers as much as two pages.
  else if (a.startsWith("--url=")) { opts.url = a.slice(6); opts.local = true; }
}
const MOBILE = new Set(["667x375", "844x390", "390x844", "360x800", "414x896", "430x932",
                        "926x428", "375x812", "393x852", "428x926"]);

function readTypography() {
  const px = (v) => (v && v.endsWith("px") ? Number(v.slice(0, -2)) : v);
  /** Layout box relative to the card element, so both sides are comparable. */
  const localBox = (el, root) => {
    let x = 0, y = 0, n = el;
    while (n && n !== root) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent; }
    return [x, y, el.offsetWidth, el.offsetHeight];
  };
  const styleOf = (el, root) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      className: el.className && typeof el.className === "string" ? el.className : null,
      text: (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 70),
      fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, fontSizePx: px(cs.fontSize),
      lineHeight: cs.lineHeight, lineHeightPx: px(cs.lineHeight),
      letterSpacing: cs.letterSpacing, letterSpacingPx: px(cs.letterSpacing),
      textTransform: cs.textTransform, textAlign: cs.textAlign,
      textWrap: cs.textWrap || cs.textWrapStyle || null,
      whiteSpace: cs.whiteSpace, color: cs.color, opacity: cs.opacity,
      overflow: cs.overflow, clipPath: cs.clipPath, borderRadius: cs.borderRadius,
      padding: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].map(px),
      margin: [cs.marginTop, cs.marginRight, cs.marginBottom, cs.marginLeft].map(px),
      display: cs.display, flexDirection: cs.flexDirection,
      containerType: cs.containerType, containerName: cs.containerName,
      maxWidth: cs.maxWidth, gap: cs.gap, flexShrink: cs.flexShrink,
      justifyContent: cs.justifyContent, alignItems: cs.alignItems,
      position: cs.position, zIndex: cs.zIndex, mixBlendMode: cs.mixBlendMode,
      backgroundColor: cs.backgroundColor,
      widthPx: px(cs.width), heightPx: px(cs.height),
      rect: [r.x, r.y, r.width, r.height],
      // Line boxes, so "how many lines does the title take" is measured.
      lineBoxes: Array.from(el.getClientRects()).map((q) => [q.x, q.y, q.width, q.height]),
      localBox: root ? localBox(el, root) : null,
      // Line count from the inline boxes of the element's own text.
      lineCount: (() => {
        if (!el.firstChild || el.firstChild.nodeType !== 3) return null;
        const r = document.createRange();
        r.selectNodeContents(el);
        return r.getClientRects().length;
      })(),
    };
  };

  // The perspective container, the scene root, and every card.
  let container = null, root = null;
  for (const d of document.querySelectorAll("div")) {
    const cs = getComputedStyle(d);
    if (cs.perspective !== "none" && container === null) {
      container = { perspectivePx: parseFloat(cs.perspective), perspectiveOrigin: cs.perspectiveOrigin,
                    transformStyle: cs.transformStyle, overflow: cs.overflow,
                    zIndex: cs.zIndex, position: cs.position, className: d.className || null };
      const kid = d.querySelector(":scope > div");
      if (kid) {
        const ks = getComputedStyle(kid);
        root = { className: kid.className || null, transform: ks.transform,
                 transformStyle: ks.transformStyle, childCount: kid.children.length };
      }
    }
  }

  const cards = [];
  const all = Array.from(document.querySelectorAll("div"));
  for (let index = 0; index < all.length; index += 1) {
    const d = all[index];
    const cs = getComputedStyle(d);
    if (!cs.transform.startsWith("matrix3d")) continue;
    const m = cs.transform.slice(9, -1).split(",").map(Number);
    if (m.length !== 16) continue;
    const text = (d.innerText || "").replace(/\s+/g, " ").trim();
    const codes = text.match(/ILG[—-]\s?\d+/g) || [];
    if (codes.length !== 1) continue;          // the scene root carries them all
    const code = Number(text.match(/ILG[—-]\s?(\d+)/)[1]);
    const self = styleOf(d);
    // The CSS3D object's own scale: the basis column norms of the matrix.
    const norm = (a, b, c) => Math.hypot(m[a], m[b], m[c]);
    const children = [];
    const walk = (el, depth) => {
      for (let i = 0; i < el.children.length; i += 1) {
        const kid = el.children[i];
        children.push({ depth, domIndex: i, ...styleOf(kid, d) });
        if (depth < 5) walk(kid, depth + 1);
      }
    };
    walk(d, 0);
    cards.push({
      code, domIndex: index, container: self,
      objectScale: [norm(0, 1, 2), norm(4, 5, 6), norm(8, 9, 10)],
      translation: [m[12], m[13], m[14]],
      backfaceVisibility: cs.backfaceVisibility, transformStyle: cs.transformStyle,
      willChange: cs.willChange, children,
    });
  }
  const footer = document.querySelector("footer");
  const footerTree = [];
  if (footer) {
    const walkFooter = (el, depth) => {
      for (let i = 0; i < el.children.length; i += 1) {
        const kid = el.children[i];
        footerTree.push({ depth, domIndex: i, ...styleOf(kid) });
        if (depth < 4) walkFooter(kid, depth + 1);
      }
    };
    walkFooter(footer, 0);
  }
  // Integrated Visual Sprint 1 §八: LOADED-face proof, not CSS-declaration
  // proof. For every distinct (family stack, weight, size) among the first
  // card's text elements and the footer: does document.fonts.check() pass,
  // and does the first family in the stack actually shape glyphs? The
  // detector is the classic two-fallback width compare -- a family that did
  // not load makes '"X", serif' and '"X", monospace' render their different
  // fallbacks, so equal widths across both (and both differing from the bare
  // fallbacks) prove X itself shaped the text. actualBoundingBox of a probe
  // string records the glyph bounds the loaded face produces.
  const fontProof = (() => {
    const tuples = new Map();
    const collect = (el) => {
      if (!el || !(el.innerText || "").trim()) return;
      const cs = getComputedStyle(el);
      const key = `${cs.fontFamily}|${cs.fontWeight}|${cs.fontSize}`;
      if (!tuples.has(key)) tuples.set(key, { family: cs.fontFamily, weight: cs.fontWeight,
        sizePx: px(cs.fontSize), sampleText: (el.innerText || "").trim().slice(0, 24),
        className: typeof el.className === "string" ? el.className : null });
    };
    // A VISIBLE card: culled labels are display:none and innerText (which is
    // render-aware) reads empty on them, so the first [data-slot] in DOM
    // order can be a hidden one that yields no tuples at all.
    const firstCard = Array.from(document.querySelectorAll("[data-slot], [data-ilg]"))
      .find((d) => (d.innerText || "").trim())
      ?? Array.from(document.querySelectorAll("div")).find((d) =>
        getComputedStyle(d).transform.startsWith("matrix3d") && /ILG/.test(d.innerText || ""));
    if (firstCard) for (const el of firstCard.querySelectorAll("*")) collect(el);
    const foot = document.querySelector("footer");
    if (foot) { collect(foot); for (const el of foot.querySelectorAll("*")) collect(el); }
    const canvas = document.createElement("canvas");
    const ctx2 = canvas.getContext("2d");
    const PROBE = "Refraction Study 0123 waves ILG";
    const rows = [];
    for (const t of tuples.values()) {
      const first = t.family.split(",")[0].trim().replace(/^"|"$/g, "");
      const w = /^\d+$/.test(t.weight) ? t.weight : "400";
      const size = Math.max(16, Math.round(t.sizePx || 16));
      const width = (stack) => { ctx2.font = `${w} ${size}px ${stack}`; return ctx2.measureText(PROBE).width; };
      const wSerif = width(`"${first}", serif`);
      const wMono = width(`"${first}", monospace`);
      const bareSerif = width("serif");
      const bareMono = width("monospace");
      const firstLoaded = Math.abs(wSerif - wMono) < 0.01
        && Math.abs(wSerif - bareSerif) > 0.01 && Math.abs(wMono - bareMono) > 0.01;
      ctx2.font = `${w} ${size}px ${t.family}`;
      const m = ctx2.measureText("RgILG—01");
      rows.push({
        ...t, firstFamily: first,
        fontsCheck: document.fonts && document.fonts.check
          ? document.fonts.check(`${w} ${size}px "${first}"`) : null,
        firstFamilyShapesText: firstLoaded,
        stackWidthPx: +width(t.family).toFixed(3),
        glyphBounds: {
          ascent: +m.actualBoundingBoxAscent.toFixed(3),
          descent: +m.actualBoundingBoxDescent.toFixed(3),
          left: +m.actualBoundingBoxLeft.toFixed(3),
          right: +m.actualBoundingBoxRight.toFixed(3),
        },
      });
    }
    return rows;
  })();
  return {
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio, userAgent: navigator.userAgent,
    container, root, cards, fontProof,
    // DOM order is the paint order for a CSS3D layer that does not sort.
    cardDomOrder: cards.map((c) => ({ code: c.code, domIndex: c.domIndex, tz: c.translation[2] })),
    footer: footer ? styleOf(footer) : null,
    footerTree,
    fonts: Array.from(document.fonts || []).map((f) => ({ family: f.family, weight: f.weight,
      style: f.style, status: f.status })),
    styleSheetHrefs: Array.from(document.styleSheets).map((s) => s.href).filter(Boolean),
  };
}

async function waitReady(page, timeoutMs = 90_000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const s = await page.evaluate(() => {
      const m = (document.body?.innerText || "").match(/(\d+)\s*%/);
      return { p: m ? Number(m[1]) : null, c: !!document.querySelector("canvas") };
    });
    if (s.c && (s.p === null || s.p >= 100)) return true;
    await page.waitForTimeout(120);
  }
  return false;
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const report = { target: opts.url, isLocal: opts.local, capturedAt: new Date().toISOString(),
  method: "computed style on the Target's own CSS3D label elements, read-only",
  viewports: [], errors: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = MOBILE.has(vp);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
    isMobile: mobile, hasTouch: mobile });
  const page = await ctx.newPage();
  try {
    await page.goto(opts.url, { waitUntil: "load", timeout: 90_000 });
    if (opts.local) {
      await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
                                 undefined, { timeout: 180_000 });
      await page.waitForTimeout(3200);
      await page.evaluate(() => {
        window.__ILG_QA__.setAdaptiveQuality(false);
        window.__ILG_QA__.setQuality("high");
        window.__ILG_QA__.setPointer(0, 0);
        window.__ILG_QA__.pause();
        window.__ILG_QA__.setOffset(0, 0);
        window.__ILG_QA__.renderOnce();
      });
    } else {
      await waitReady(page);
      await page.waitForTimeout(opts.settle);
    }
    const state = await page.evaluate(readTypography);
    if (opts.shots) await page.screenshot({ path: path.join(opts.out, `${vp}.png`) });
    report.viewports.push({ id: vp, viewport: [w, h], mobile, ...state });
    const c = state.cards[0];
    console.log(`${vp}  cards=${state.cards.length}  box=${c?.container.widthPx}x${c?.container.heightPx}  scale=${c?.objectScale.map((n) => n.toFixed(4))}  pad=${c?.container.padding}`);
  } catch (e) {
    report.errors.push(`${vp}: ${e.message}`);
    console.error(`FAILED ${vp}: ${e.message}`);
  }
  await ctx.close();
}
await browser.close();
await writeFile(path.join(opts.out, "target-typography.json"), JSON.stringify(report, null, 2));
console.log(`-> ${opts.out}/target-typography.json  (${report.errors.length} errors)`);
