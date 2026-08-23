/**
 * Visual Convergence Sprint 2 §三 -- the matched-content core.
 *
 * Sprint 1 compared two pages that were each showing their own clips and their
 * own headlines. That is a fair product comparison and a useless optical one:
 * a dark shoulder can be the glass or it can be the clip behind it, and no
 * amount of ROI statistics separates those two when the clips differ. This
 * module removes both variables.
 *
 * MEDIA. Reuses the O2 shared-media core verbatim (`o2_media_routes.mjs`):
 * the Target's mux HLS requests and our /clips/*.mp4 requests are both
 * fulfilled from ONE locally generated asset whose H.264 elementary stream is
 * byte-identical across the two containers. Six asset categories are exposed
 * here, one per §三A row. Both sides are then frozen at the same media time.
 *
 * COPY. One injector, run verbatim on both pages. Every card's text leaves are
 * discovered in document order and rewritten with the SAME strings -- except
 * the leading `ILG—NN` code, which is each page's own slot identity and is the
 * key everything else pairs on. A MutationObserver re-asserts the strings if
 * either page's own renderer writes over them, and `readCopyRows` reads the
 * strings BACK out of the DOM at capture time so "same copy" is a measurement
 * rather than an intention.
 *
 * LABELS. The glass pass hides the CSS3D layer on both sides by dropping the
 * opacity of the cards' common ancestor -- one element, no per-card writes,
 * so neither page's own visibility bookkeeping is disturbed.
 */
import { createHash } from "node:crypto";
import {
  MEDIA_DIR, loadAsset, installTargetRoutes, installLocalRoutes,
  TARGET_VIDEO_HOOK, freezeTarget, decodedFrame,
} from "./o2_media_routes.mjs";

export const TARGET_URL = "https://infinite-liquid-glass.shader.se/?v=2";
export const LOCAL_ORIGIN = "http://127.0.0.1:5293";
export const MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
  + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

/** §三A: the six required content categories, mapped onto the O2 asset set. */
export const MEDIA_SET = [
  { key: "dark-cinematic", asset: "dark-highlight",
    why: "near-black field with one blown highlight -- the dark-shoulder case" },
  { key: "bright-lowsat", asset: "bright-lowsat",
    why: "high-key, low saturation -- where a milky glass reads worst" },
  { key: "warm-skin", asset: "warm-skin", why: "warm mid-tone content" },
  { key: "cool-blue", asset: "cool-blue", why: "cool mid-tone content" },
  { key: "high-texture", asset: "hf-checker",
    why: "8 px checker -- every dispersion and blur artefact is legible" },
  { key: "bw-structured", asset: "bw-split",
    why: "hard black/white edge -- edge transfer and shoulder placement" },
];

/**
 * §三B: the injected copy. ONE string set for both pages.
 *
 * The deck is deliberately long enough to wrap: two lines in a desktop card,
 * three in a portrait-phone card, so §一.5's "actual line breaking" is
 * exercised rather than assumed. The strings are our own; the Target's own
 * headlines are never copied into this repo.
 */
export const MATCHED_COPY = {
  category: "Matched content",
  metaRightA: "Selected work",
  metaRightB: "2026",
  title: "Quiet Circuit",
  deck: "A long exposure of empty platforms after rain, held open until the last train stops.",
};

/**
 * In-page: discover cards, rewrite their copy, keep it rewritten.
 *
 * A card is any element carrying a matrix3d transform whose text contains
 * exactly one ILG code -- the same predicate the M2/M3 recorders use, so card
 * discovery here and card discovery in the trajectory instrument cannot drift.
 */
export const COPY_INJECTOR = `(() => {
  const S = { copy: null, cards: [], obs: null, reasserts: 0, failures: [] };
  window.__VC2 = S;

  S.discover = () => {
    const out = [];
    for (const d of document.querySelectorAll("div")) {
      if (!d.style.transform || !d.style.transform.includes("matrix3d")) continue;
      const text = (d.textContent || "").replace(/\\s+/g, " ").trim();
      const hits = text.match(/ILG[\\u2014-]\\s?(\\d+)/g) || [];
      if (hits.length !== 1) continue;
      out.push({ code: Number(text.match(/ILG[\\u2014-]\\s?(\\d+)/)[1]), el: d });
    }
    out.sort((a, b) => a.code - b.code);
    S.cards = out;
    return out.length;
  };

  /** Text-bearing leaves of one card, in document order. */
  S.leaves = (root) => {
    const acc = [];
    const walk = (el) => {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3)
        .map((n) => n.textContent).join("").trim();
      if (own) acc.push(el);
      for (const k of el.children) walk(k);
    };
    walk(root);
    return acc;
  };

  /** The card's copy as the DOM currently holds it, minus the ILG code. */
  S.rowOf = (c) => {
    const ls = S.leaves(c.el);
    return { code: c.code, n: ls.length,
             text: ls.slice(1).map((e) => e.textContent.replace(/\\s+/g, " ").trim()) };
  };

  S.write = () => {
    S.failures = [];
    for (const c of S.cards) {
      const ls = S.leaves(c.el);
      // 6 leaves: ILG code, category, "Selected work", year, title, deck.
      if (ls.length !== 6) { S.failures.push({ code: c.code, leaves: ls.length }); continue; }
      const want = [S.copy.category, S.copy.metaRightA, S.copy.metaRightB,
                    S.copy.title, S.copy.deck];
      for (let i = 0; i < want.length; i += 1) {
        if (ls[i + 1].textContent !== want[i]) ls[i + 1].textContent = want[i];
      }
    }
  };

  S.apply = (copy) => {
    S.copy = copy;
    const n = S.discover();
    S.write();
    if (S.obs) S.obs.disconnect();
    S.obs = new MutationObserver(() => {
      S.reasserts += 1;
      // Re-discover: a page that recycles card elements can hand a slot a
      // fresh subtree, and a stale element list would silently stop writing.
      S.discover();
      S.write();
    });
    for (const c of S.cards) {
      S.obs.observe(c.el, { childList: true, characterData: true, subtree: true });
    }
    return { cards: n, failures: S.failures };
  };

  S.read = () => ({
    cards: S.cards.length, reasserts: S.reasserts, failures: S.failures,
    rows: S.cards.map(S.rowOf),
    visible: S.cards.filter((c) => c.el.style.visibility !== "hidden").map((c) => c.code),
  });

  /** The cards' common ancestor -- the CSS3D layer root on both pages. */
  S.labelRoot = () => {
    if (!S.cards.length) S.discover();
    if (!S.cards.length) return null;
    const chain = (el) => { const a = []; for (let n = el; n; n = n.parentElement) a.push(n); return a; };
    let common = chain(S.cards[0].el);
    for (const c of S.cards.slice(1)) {
      const set = new Set(chain(c.el));
      common = common.filter((n) => set.has(n));
    }
    return common[0] ?? null;
  };

  S.setLabels = (on) => {
    const root = S.labelRoot();
    if (!root) return false;
    if (on) root.style.removeProperty("opacity");
    else root.style.setProperty("opacity", "0", "important");
    return true;
  };
  return true;
})()`;

const sha256 = (s) => createHash("sha256").update(s).digest("hex");
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Load one §三A asset by its category key. */
export function assetFor(key) {
  const row = MEDIA_SET.find((m) => m.key === key);
  if (!row) throw new Error(`unknown media category ${key}`);
  return { ...row, asset: loadAsset(row.asset, MEDIA_DIR) };
}

/**
 * Open a matched context on one side. Media routes and the two init scripts
 * are installed BEFORE the first navigation, so nothing unmatched is ever
 * decoded and no card is ever painted with its own copy.
 */
export async function openMatched(browser, { side, url, vp, asset, mediaLog }) {
  const [width, height] = vp.split("x").map(Number);
  const touch = width < 768;
  const ctx = await browser.newContext({
    viewport: { width, height }, deviceScaleFactor: 1,
    hasTouch: touch, isMobile: touch, ...(touch ? { userAgent: MOBILE_UA } : {}),
  });
  if (asset) {
    if (side === "target") await installTargetRoutes(ctx, asset, mediaLog);
    else await installLocalRoutes(ctx, asset, mediaLog);
  }
  if (side === "target") await ctx.addInitScript(TARGET_VIDEO_HOOK);
  await ctx.addInitScript(COPY_INJECTOR);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  await page.goto(url, { waitUntil: "load", timeout: 150000 });
  if (side === "local") {
    await page.waitForFunction(() => window.__ILG_QA__?.getAssetState?.()?.ready === true,
      undefined, { timeout: 200000 });
  }
  await page.waitForTimeout(side === "target" ? 9000 : 5000);
  return { ctx, page, errors, touch, width, height };
}

/**
 * Pin everything §三C names, in the same order on both sides, and hand back
 * the readback that proves it: media state, copy rows, runtime state.
 */
export async function pinMatched(page, { side, labels, mediaTime = 2, pointer = null }) {
  const media = side === "target"
    ? await freezeTarget(page, mediaTime)
    : await page.evaluate(async (t) => {
        window.__ILG_QA__.setMediaTimeAndFreeze(t);
        await new Promise((r) => setTimeout(r, 900));
        return [...document.querySelectorAll("video")].map((v) => ({
          currentTime: +v.currentTime.toFixed(4), paused: v.paused,
          videoWidth: v.videoWidth, videoHeight: v.videoHeight,
          duration: +(+v.duration).toFixed(3), readyState: v.readyState,
        }));
      }, mediaTime);
  const copy = await page.evaluate((c) => window.__VC2.apply(c), MATCHED_COPY);
  const labelsOk = await page.evaluate((on) => window.__VC2.setLabels(on), labels);
  if (pointer) await page.mouse.move(pointer[0], pointer[1]);
  await page.waitForTimeout(700);
  return { media, copy, labelsOk };
}

/** Read the matched state back out of the live page. */
export async function readMatched(page, side) {
  const dom = await page.evaluate(() => {
    const S = window.__VC2;
    const r = S.read();
    return {
      ...r,
      viewport: [innerWidth, innerHeight], dpr: devicePixelRatio,
      coarsePointer: matchMedia("(pointer: coarse)").matches,
      videos: [...document.querySelectorAll("video")].map((v) => ({
        t: +v.currentTime.toFixed(4), w: v.videoWidth, h: v.videoHeight, paused: v.paused,
      })),
      targetVideos: (window.__o2vids ?? []).map((v) => ({
        t: +v.currentTime.toFixed(4), w: v.videoWidth, h: v.videoHeight, paused: v.paused,
      })),
    };
  });
  const engine = side === "local"
    ? await page.evaluate(() => {
        const q = window.__ILG_QA__;
        const s = q.getState();
        return { quality: s.quality, scrollX: s.scrollX, scrollY: s.scrollY,
                 adaptive: q.getAdaptiveState().enabled,
                 optics: q.getOpticsState(), culling: q.getRenderCullingTruth() };
      })
    : null;
  // Copy identity is the ROW TEXT ONLY -- the ILG code is each page's own slot
  // identity and is deliberately excluded from the hash.
  const bodies = dom.rows.map((r) => JSON.stringify(r.text));
  const uniq = [...new Set(bodies)];
  return { ...dom, engine,
           copyBodySha: uniq.length === 1 ? sha256(uniq[0]) : null,
           copyBodies: uniq.length === 1 ? uniq[0] : uniq.slice(0, 4),
           copyUniform: uniq.length === 1 };
}

/**
 * The page's own decoded video frame, as PNG bytes.
 *
 * `decodedFrame` (O2) reduces the frame to landmarks and one FNV hash, which
 * answers "is this the right asset" but cannot answer "how far apart are the
 * two decodes" when the hashes differ -- and they do differ on one asset,
 * because a progressive mp4 and a CMAF segmentation of the SAME elementary
 * stream can leave 1-LSB decode differences on a shallow gradient. Taking the
 * frame itself lets the difference be measured instead of asserted away.
 */
export async function decodedPng(page, side) {
  return page.evaluate((k) => {
    const v = k === "target" ? (window.__o2vids ?? [])[0] : document.querySelector("video");
    if (!v || !v.videoWidth) return null;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d", { willReadFrequently: true }).drawImage(v, 0, 0);
    try { return c.toDataURL("image/png").split(",")[1]; } catch { return null; }
  }, side);
}

export { decodedFrame, freezeTarget, sha256 };
