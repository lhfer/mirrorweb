import type { ContentCard, ContentManifest, MediaAsset } from "./domain";

const CARD_ROWS: Array<[
  string,
  string,
  string,
  string,
  string,
  [string, string, string, string],
]> = [
  ["ILG—11", "FIELD STUDY", "Quiet Circuit", "A long exposure of empty platforms after rain.", "#d7ff3f", ["#1a1f2b", "#6b7c8a", "#d7c4a3", "#f2efe8"]],
  ["ILG—12", "EDITORIAL", "Night Index", "Street lamps counted like a private census.", "#ff9ad5", ["#07060c", "#2a1b4a", "#c46bff", "#f5e6ff"]],
  ["ILG—13", "CULTURAL PLATFORM", "Soft Power", "Silk, concrete, and a borrowed skyline.", "#8ff7ff", ["#10222a", "#1f6f7a", "#9ad7d4", "#e8fffb"]],
  ["ILG—14", "ARCHITECTURE", "Glass House", "Warm rooms stacked against a late sun.", "#ffcc66", ["#2a1408", "#c45a18", "#f0a35a", "#ffe7c2"]],
  ["ILG—15", "DIGITAL PRODUCT", "Slow Signal", "Hands, pigment, and a delayed reply.", "#d7ff3f", ["#12100e", "#5a5348", "#c9b59a", "#f4efe6"]],
  ["ILG—16", "EDITORIAL", "Field Notes", "A city that only appears after midnight.", "#9ad7ff", ["#05060c", "#1a2a4a", "#7aa0d4", "#e4ecff"]],
  ["ILG—17", "IDENTITY", "No Fixed Form", "A mark that refuses a single outline.", "#ffd18a", ["#1b120c", "#8a4b22", "#e0a36b", "#fff1dc"]],
  ["ILG—18", "CAMPAIGN", "Free State", "Open water under a borrowed violet hour.", "#c9a6ff", ["#12081c", "#4b2a7a", "#b48cff", "#f3e9ff"]],
  ["ILG—19", "SPECULATIVE DESIGN", "Infinite City", "Waves that keep rewriting the same street.", "#8ff7ff", ["#061018", "#16324a", "#7eb6c9", "#e7f6ff"]],
  ["ILG—20", "WORKPLACE", "Outer Office", "Desks facing a window that never quite opens.", "#ff9ad5", ["#101014", "#3a3a48", "#b9b4c9", "#f2f0f6"]],
  ["ILG—21", "CAMPAIGN", "New Rituals", "Morning light rehearsed until it looks accidental.", "#d7ff3f", ["#1a160c", "#7a5a18", "#e6c85a", "#fff6d0"]],
  ["ILG—22", "CULTURAL PLATFORM", "Common Sky", "Shared weather over private rooftops.", "#8ff7ff", ["#0a1820", "#2a5a6a", "#8ec8c4", "#e8fffa"]],
  ["ILG—23", "ARCHITECTURE", "Elsewhere", "A lobby built for people who are leaving.", "#ffcc66", ["#141010", "#5a4038", "#d4b09a", "#fff4ec"]],
  ["ILG—24", "EDITORIAL", "Echo Chamber", "Reflections stacked until the source is gone.", "#ff9ad5", ["#0c0610", "#4a1840", "#e070b0", "#ffe6f4"]],
  ["ILG—25", "FIELD STUDY", "Second Nature", "Moss taking the corners of a steel stair.", "#9dff7a", ["#08140c", "#1f4a28", "#7dba6a", "#e8ffd8"]],
  ["ILG—26", "DIGITAL PRODUCT", "Drift State", "A cursor that keeps missing the same button.", "#8ff7ff", ["#0a1020", "#24386a", "#7aa8ff", "#e8f0ff"]],
  ["ILG—27", "IDENTITY", "Hard Light", "One lamp, four walls, no compromise.", "#ffcc66", ["#1c1008", "#8a3a10", "#f0a040", "#ffe8c8"]],
  ["ILG—28", "CAMPAIGN", "Public Dream", "A plaza that only fills after closing time.", "#c9a6ff", ["#100818", "#3a2458", "#a888e0", "#f4ecff"]],
  ["ILG—29", "SPECULATIVE DESIGN", "Low Gravity", "Furniture that forgot which way is down.", "#9ad7ff", ["#081018", "#204060", "#88c0e0", "#e8f8ff"]],
  ["ILG—30", "EDITORIAL", "Deep Surface", "A photograph that keeps its distance.", "#d7ff3f", ["#10140c", "#3a4a28", "#b8c878", "#f4ffe0"]],
  ["ILG—31", "WORKPLACE", "Near Future", "The next version of a room we already know.", "#ff9ad5", ["#141018", "#403050", "#c8a0c8", "#f8eef8"]],
  ["ILG—32", "FIELD STUDY", "Afterimage", "What remains when the shutter finally closes.", "#8ff7ff", ["#0c1018", "#2a3848", "#90a8b8", "#eef4f8"]],
  ["ILG—33", "ARCHITECTURE", "Unfinished", "Scaffolding kept as the final ornament.", "#ffcc66", ["#18140c", "#6a4a20", "#d4a060", "#fff0d4"]],
  ["ILG—34", "CULTURAL PLATFORM", "Future Folklore", "A story told with lights instead of names.", "#c9a6ff", ["#100c1c", "#3a2870", "#9070e8", "#eee6ff"]],
];

const NOW = "2026-08-23T00:00:00.000Z";

export const SEED_MEDIA: MediaAsset[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    originalName: "niulai-intro.mp4",
    storagePath: "seed/niulai-intro.mp4",
    posterPath: "",
    mimeType: "video/mp4",
    sizeBytes: 614135,
    width: 960,
    height: 540,
    durationMs: 5000,
    status: "ready",
    mediaUrl: "/clips/niulai-intro.mp4",
    createdAt: NOW,
    updatedAt: NOW,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    originalName: "cursor-niulai.mp4",
    storagePath: "seed/cursor-niulai.mp4",
    posterPath: "",
    mimeType: "video/mp4",
    sizeBytes: 1346708,
    width: 960,
    height: 556,
    durationMs: 5000,
    status: "ready",
    mediaUrl: "/clips/cursor-niulai.mp4",
    createdAt: NOW,
    updatedAt: NOW,
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    originalName: "pelican-ai.mp4",
    storagePath: "seed/pelican-ai.mp4",
    posterPath: "",
    mimeType: "video/mp4",
    sizeBytes: 678999,
    width: 960,
    height: 540,
    durationMs: 5000,
    status: "ready",
    mediaUrl: "/clips/pelican-ai.mp4",
    createdAt: NOW,
    updatedAt: NOW,
  },
];

function createCards(): ContentCard[] {
  return CARD_ROWS.map(([code, category, title, deck, accent, palette], index) => {
    const media = SEED_MEDIA[index % SEED_MEDIA.length];
    const pelican = media.id === "33333333-3333-4333-8333-333333333333";
    return {
      id: code.replace("—", "-").toLocaleLowerCase(),
      code,
      category,
      title,
      deck,
      accent,
      palette,
      mediaAssetId: media.id,
      mediaUrl: media.mediaUrl,
      focusX: 0.5,
      focusY: pelican ? 0.46 : 0.5,
      zoom: pelican ? 1.06 : 1,
      enabled: true,
      sortOrder: index,
    };
  });
}

export function createSeedManifest(): ContentManifest {
  return {
    schemaVersion: 1,
    version: 1,
    cards: createCards(),
    site: {
      footerCaption: "AN EXPERIMENT BY",
      brandText: "ATELIER",
      brandUrl: "https://shader.se/",
      ctaLabel: "Book a Call",
      ctaUrl: "https://cal.com/simon-hedlund-kglzne",
      loaderBrandText: "ATELIER",
    },
  };
}
