/**
 * The deterministic shared-media core: both pages consume the SAME locally
 * generated asset bytes through Playwright routing.
 *
 * Target lane: the page requests https://stream.mux.com/{playbackId}.m3u8
 * (hls.js / MSE -- every request is fetch/XHR and interceptable). Every
 * playlist is fulfilled with OUR CMAF rendition of the chosen asset
 * (segment URIs rewritten under __o2/ on the same host and also fulfilled
 * here); the mux manifest/chunk CDN hosts are aborted so nothing real can
 * leak in. The rendition was remuxed -c copy from the asset mp4, so its
 * H.264 elementary stream is byte-identical to what the local lane gets
 * (asserted at generation time, SHA in media-manifest.json).
 *
 * Local lane: the page requests /clips/*.mp4 progressively with Range
 * headers; all three clip URLs are fulfilled with the SAME asset mp4,
 * with real 206 slicing (Chromium's media stack expects honoured ranges).
 *
 * Every fulfilment is logged {url, file, sha256, bytes, status} -- the
 * "Target response SHA / Local response SHA" record is of bytes AS SERVED
 * (the rewritten playlist's SHA is of the served body, not the on-disk
 * generator output).
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const MEDIA_DIR = path.join(REPO, "artifacts/optics-o2/media");

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

export function loadAsset(name) {
  const manifest = JSON.parse(
    readFileSync(path.join(MEDIA_DIR, "media-manifest.json"), "utf8"));
  const entry = manifest.assets.find((a) => a.name === name);
  if (!entry) throw new Error(`unknown asset ${name}`);
  const dir = path.join(MEDIA_DIR, name);
  const mp4 = readFileSync(path.join(dir, `${name}.mp4`));
  const rawPlaylist = readFileSync(path.join(dir, "hls/media.m3u8"), "utf8");
  const servedPlaylist = rawPlaylist
    .replace(/#EXT-X-MAP:URI="init\.mp4"/, '#EXT-X-MAP:URI="__o2/init.mp4"')
    .replace(/^(seg\d+\.m4s)$/gm, "__o2/$1");
  const files = new Map();
  files.set("init.mp4", readFileSync(path.join(dir, "hls/init.mp4")));
  for (const seg of entry.hls.segments) {
    files.set(seg.file, readFileSync(path.join(dir, "hls", seg.file)));
  }
  return {
    name, entry, mp4, mp4Sha: sha256(mp4),
    servedPlaylist, servedPlaylistSha: sha256(Buffer.from(servedPlaylist)),
    files,
  };
}

/** Route the Target context so every mux video request serves `asset`. */
export async function installTargetRoutes(ctx, asset, log) {
  await ctx.route("https://stream.mux.com/**", async (route) => {
    const u = route.request().url();
    if (u.includes("/__o2/")) {
      const f = u.split("/__o2/")[1].split("?")[0];
      const body = asset.files.get(f);
      if (!body) return route.fulfill({ status: 404, body: "" });
      log?.push({ url: u, file: `${asset.name}/hls/${f}`, sha256: sha256(body),
                  bytes: body.length, status: 200 });
      return route.fulfill({ status: 200, contentType: "video/mp4",
        headers: { "access-control-allow-origin": "*", "cache-control": "no-store" },
        body });
    }
    if (u.endsWith(".m3u8")) {
      log?.push({ url: u, file: `${asset.name}/media.m3u8 (served form)`,
                  sha256: asset.servedPlaylistSha,
                  bytes: asset.servedPlaylist.length, status: 200 });
      return route.fulfill({ status: 200,
        contentType: "application/vnd.apple.mpegurl",
        headers: { "access-control-allow-origin": "*", "cache-control": "no-store" },
        body: asset.servedPlaylist });
    }
    return route.abort();
  });
  // Nothing real from the mux CDN may reach the page.
  await ctx.route(/https:\/\/(manifest|chunk)-[^/]*\.mux\.com\/.*/,
    (route) => route.abort());
}

/** Route a local-page context so every /clips/*.mp4 serves `asset`. */
export async function installLocalRoutes(ctx, asset, log) {
  await ctx.route("**/clips/*.mp4", async (route) => {
    const u = route.request().url();
    const range = route.request().headers()["range"];
    const body = asset.mp4;
    if (range) {
      const m = /bytes=(\d+)-(\d*)/.exec(range);
      const start = m ? parseInt(m[1], 10) : 0;
      const end = m && m[2] ? Math.min(parseInt(m[2], 10), body.length - 1)
                            : body.length - 1;
      const slice = body.subarray(start, end + 1);
      log?.push({ url: u, file: `${asset.name}/${asset.name}.mp4`,
                  sha256: asset.mp4Sha, range: `${start}-${end}`,
                  bytes: slice.length, status: 206 });
      return route.fulfill({ status: 206, contentType: "video/mp4",
        headers: {
          "accept-ranges": "bytes",
          "content-range": `bytes ${start}-${end}/${body.length}`,
          "cache-control": "no-store",
        },
        body: slice });
    }
    log?.push({ url: u, file: `${asset.name}/${asset.name}.mp4`,
                sha256: asset.mp4Sha, bytes: body.length, status: 200 });
    return route.fulfill({ status: 200, contentType: "video/mp4",
      headers: { "accept-ranges": "bytes", "cache-control": "no-store" },
      body });
  });
}

/** addInitScript source: capture the Target's DETACHED video elements. */
export const TARGET_VIDEO_HOOK = `(() => {
  window.__o2vids = [];
  const orig = document.createElement.bind(document);
  document.createElement = (tag, ...rest) => {
    const el = orig(tag, ...rest);
    if (String(tag).toLowerCase() === "video") window.__o2vids.push(el);
    return el;
  };
})()`;

/** Freeze every captured Target video at `t` and report their state. */
export async function freezeTarget(page, t) {
  return page.evaluate(async (time) => {
    const vids = window.__o2vids ?? [];
    await Promise.all(vids.map((v) => new Promise((res) => {
      v.pause();
      const done = () => { v.onseeked = null; res(); };
      v.onseeked = done;
      v.currentTime = time;
      setTimeout(done, 4000);
    })));
    await new Promise((r) => setTimeout(r, 300));
    return vids.map((v) => ({
      currentTime: +v.currentTime.toFixed(4), paused: v.paused,
      videoWidth: v.videoWidth, videoHeight: v.videoHeight,
      duration: +(+v.duration).toFixed(3), readyState: v.readyState,
    }));
  }, t);
}

/**
 * Decoded-frame proof: draw the page's first video to a canvas and sample
 * the asset's landmarks (16x16 region means) plus a full-frame hash.
 * `kind` = "target" (window.__o2vids) | "local" (document video elements).
 */
export async function decodedFrame(page, landmarks, kind) {
  return page.evaluate(async ({ lms, k }) => {
    const v = k === "target" ? (window.__o2vids ?? [])[0]
                             : document.querySelector("video");
    if (!v || !v.videoWidth) return { error: "no decodable video" };
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.drawImage(v, 0, 0);
    let data;
    try { data = g.getImageData(0, 0, c.width, c.height).data; }
    catch (e) { return { error: "canvas tainted: " + String(e).slice(0, 120) }; }
    const region = (nx, ny) => {
      const x0 = Math.max(0, Math.round(nx * c.width) - 8);
      const y0 = Math.max(0, Math.round(ny * c.height) - 8);
      let r = 0, gg = 0, b = 0, n = 0;
      for (let y = y0; y < y0 + 16; y += 1) {
        for (let x = x0; x < x0 + 16; x += 1) {
          const i = (y * c.width + x) * 4;
          r += data[i]; gg += data[i + 1]; b += data[i + 2]; n += 1;
        }
      }
      return [Math.round(r / n), Math.round(gg / n), Math.round(b / n)];
    };
    const out = {};
    for (const [name, lm] of Object.entries(lms)) out[name] = region(lm.nx, lm.ny);
    // FNV-1a over every pixel byte: cross-page decode-identity evidence.
    let h1 = 0x811c9dc5;
    for (let i = 0; i < data.length; i += 1) {
      h1 ^= data[i]; h1 = Math.imul(h1, 0x01000193) >>> 0;
    }
    return { landmarks: out, frameHashFnv1a: h1.toString(16),
             width: c.width, height: c.height };
  }, { lms: landmarks, k: kind });
}

export function landmarkVerdict(expected, got, tol = 12) {
  const rows = [];
  let pass = true;
  for (const [name, lm] of Object.entries(expected)) {
    const g = got?.[name];
    const delta = g ? Math.max(...g.map((x, i) => Math.abs(x - lm.rgb[i]))) : null;
    const ok = g !== undefined && delta <= tol;
    pass = pass && ok;
    rows.push({ landmark: name, expected: lm.rgb, got: g ?? null,
                maxChannelDelta: delta, pass: ok });
  }
  return { pass, tolerance: tol, rows };
}
