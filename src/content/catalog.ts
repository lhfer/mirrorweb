import { CLIPS } from "./VideoClips";

export type CatalogItem = {
  code: string;
  category: string;
  title: string;
  deck: string;
  accent: string;
  palette: [string, string, string, string];
  clipIndex?: number;
};

export const CATALOG: CatalogItem[] = [
  { code: "ILG—11", category: "FIELD STUDY", title: "Quiet Circuit", deck: "A long exposure of empty platforms after rain.", accent: "#d7ff3f", palette: ["#1a1f2b", "#6b7c8a", "#d7c4a3", "#f2efe8"] },
  { code: "ILG—12", category: "EDITORIAL", title: "Night Index", deck: "Street lamps counted like a private census.", accent: "#ff9ad5", palette: ["#07060c", "#2a1b4a", "#c46bff", "#f5e6ff"] },
  { code: "ILG—13", category: "CULTURAL PLATFORM", title: "Soft Power", deck: "Silk, concrete, and a borrowed skyline.", accent: "#8ff7ff", palette: ["#10222a", "#1f6f7a", "#9ad7d4", "#e8fffb"] },
  { code: "ILG—14", category: "ARCHITECTURE", title: "Glass House", deck: "Warm rooms stacked against a late sun.", accent: "#ffcc66", palette: ["#2a1408", "#c45a18", "#f0a35a", "#ffe7c2"] },
  { code: "ILG—15", category: "DIGITAL PRODUCT", title: "Slow Signal", deck: "Hands, pigment, and a delayed reply.", accent: "#d7ff3f", palette: ["#12100e", "#5a5348", "#c9b59a", "#f4efe6"] },
  { code: "ILG—16", category: "EDITORIAL", title: "Field Notes", deck: "A city that only appears after midnight.", accent: "#9ad7ff", palette: ["#05060c", "#1a2a4a", "#7aa0d4", "#e4ecff"] },
  { code: "ILG—17", category: "IDENTITY", title: "No Fixed Form", deck: "A mark that refuses a single outline.", accent: "#ffd18a", palette: ["#1b120c", "#8a4b22", "#e0a36b", "#fff1dc"] },
  { code: "ILG—18", category: "CAMPAIGN", title: "Free State", deck: "Open water under a borrowed violet hour.", accent: "#c9a6ff", palette: ["#12081c", "#4b2a7a", "#b48cff", "#f3e9ff"] },
  { code: "ILG—19", category: "SPECULATIVE DESIGN", title: "Infinite City", deck: "Waves that keep rewriting the same street.", accent: "#8ff7ff", palette: ["#061018", "#16324a", "#7eb6c9", "#e7f6ff"] },
  { code: "ILG—20", category: "WORKPLACE", title: "Outer Office", deck: "Desks facing a window that never quite opens.", accent: "#ff9ad5", palette: ["#101014", "#3a3a48", "#b9b4c9", "#f2f0f6"] },
  { code: "ILG—21", category: "CAMPAIGN", title: "New Rituals", deck: "Morning light rehearsed until it looks accidental.", accent: "#d7ff3f", palette: ["#1a160c", "#7a5a18", "#e6c85a", "#fff6d0"] },
  { code: "ILG—22", category: "CULTURAL PLATFORM", title: "Common Sky", deck: "Shared weather over private rooftops.", accent: "#8ff7ff", palette: ["#0a1820", "#2a5a6a", "#8ec8c4", "#e8fffa"] },
  { code: "ILG—23", category: "ARCHITECTURE", title: "Elsewhere", deck: "A lobby built for people who are leaving.", accent: "#ffcc66", palette: ["#141010", "#5a4038", "#d4b09a", "#fff4ec"] },
  { code: "ILG—24", category: "EDITORIAL", title: "Echo Chamber", deck: "Reflections stacked until the source is gone.", accent: "#ff9ad5", palette: ["#0c0610", "#4a1840", "#e070b0", "#ffe6f4"] },
  { code: "ILG—25", category: "FIELD STUDY", title: "Second Nature", deck: "Moss taking the corners of a steel stair.", accent: "#9dff7a", palette: ["#08140c", "#1f4a28", "#7dba6a", "#e8ffd8"] },
  { code: "ILG—26", category: "DIGITAL PRODUCT", title: "Drift State", deck: "A cursor that keeps missing the same button.", accent: "#8ff7ff", palette: ["#0a1020", "#24386a", "#7aa8ff", "#e8f0ff"] },
  { code: "ILG—27", category: "IDENTITY", title: "Hard Light", deck: "One lamp, four walls, no compromise.", accent: "#ffcc66", palette: ["#1c1008", "#8a3a10", "#f0a040", "#ffe8c8"] },
  { code: "ILG—28", category: "CAMPAIGN", title: "Public Dream", deck: "A plaza that only fills after closing time.", accent: "#c9a6ff", palette: ["#100818", "#3a2458", "#a888e0", "#f4ecff"] },
  { code: "ILG—29", category: "SPECULATIVE DESIGN", title: "Low Gravity", deck: "Furniture that forgot which way is down.", accent: "#9ad7ff", palette: ["#081018", "#204060", "#88c0e0", "#e8f8ff"] },
  { code: "ILG—30", category: "EDITORIAL", title: "Deep Surface", deck: "A photograph that keeps its distance.", accent: "#d7ff3f", palette: ["#10140c", "#3a4a28", "#b8c878", "#f4ffe0"] },
  { code: "ILG—31", category: "WORKPLACE", title: "Near Future", deck: "The next version of a room we already know.", accent: "#ff9ad5", palette: ["#141018", "#403050", "#c8a0c8", "#f8eef8"] },
  { code: "ILG—32", category: "FIELD STUDY", title: "Afterimage", deck: "What remains when the shutter finally closes.", accent: "#8ff7ff", palette: ["#0c1018", "#2a3848", "#90a8b8", "#eef4f8"] },
  { code: "ILG—33", category: "ARCHITECTURE", title: "Unfinished", deck: "Scaffolding kept as the final ornament.", accent: "#ffcc66", palette: ["#18140c", "#6a4a20", "#d4a060", "#fff0d4"] },
  { code: "ILG—34", category: "CULTURAL PLATFORM", title: "Future Folklore", deck: "A story told with lights instead of names.", accent: "#c9a6ff", palette: ["#100c1c", "#3a2870", "#9070e8", "#eee6ff"] },
];

export function catalogAt(i: number, j: number): CatalogItem {
  const n = CATALOG.length;
  const index = ((i * 7 + j * 13) % n + n) % n;
  return {
    ...CATALOG[index],
    clipIndex: index % CLIPS.length,
  };
}
