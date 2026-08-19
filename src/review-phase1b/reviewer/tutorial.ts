/**
 * Step 0: the visual tutorial.
 *
 * It explains the four optical zones with a synthetic card, shows the same
 * zones on a real Frozen target crop, contrasts one correct annotation with
 * one wrong annotation, and lists the things that must never be treated as a
 * boundary. It is pure explanation: nothing here writes an annotation.
 */

import { t } from "./i18n";

const SVG_NS = "http://www.w3.org/2000/svg";

function element<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attributes: Record<string, string | number>,
  text?: string,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

export interface SyntheticCardOptions {
  width?: number;
  height?: number;
  /** Draw the halo, highlight and typography distractors. */
  distractors?: boolean;
  /** Where the three boundaries are drawn, as a fraction of the card height. */
  boundaries?: [number, number, number];
  labels?: boolean;
  variant?: "correct" | "wrong" | "plain";
}

/**
 * A schematic glass card: four concentric optical zones plus the visual
 * distractors a reviewer must learn to ignore.
 */
export function syntheticCard(options: SyntheticCardOptions = {}): SVGSVGElement {
  const width = options.width ?? 420;
  const height = options.height ?? 260;
  const boundaries = options.boundaries ?? [0.045, 0.11, 0.2];
  const svg = element("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "rv-figure",
    role: "img",
    "aria-label": t("tutorialSynthetic"),
  });
  const labelled = options.labels === true;
  const inset = Math.min(width, height);
  const cardX = width * 0.08;
  const cardY = height * 0.14;
  const cardW = width * (labelled ? 0.6 : 0.84);
  const cardH = height * 0.72;

  if (options.distractors !== false) {
    svg.append(element("rect", {
      x: cardX - inset * 0.06,
      y: cardY - inset * 0.06,
      width: cardW + inset * 0.12,
      height: cardH + inset * 0.12,
      rx: 26,
      class: "fig-halo",
    }));
  }

  const bands: Array<[number, string]> = [
    [0, "fig-sidewall"],
    [boundaries[0], "fig-rim"],
    [boundaries[1], "fig-shoulder"],
    [boundaries[2], "fig-center"],
  ];
  for (const [ratio, className] of bands) {
    const pad = ratio * inset;
    svg.append(element("rect", {
      x: cardX + pad,
      y: cardY + pad,
      width: Math.max(2, cardW - pad * 2),
      height: Math.max(2, cardH - pad * 2),
      rx: Math.max(2, 20 - pad * 0.5),
      class: className,
    }));
  }

  if (options.distractors !== false) {
    svg.append(element("path", {
      d: `M ${cardX + cardW * 0.16} ${cardY + cardH * 0.2} Q ${cardX + cardW * 0.42} ${cardY + cardH * 0.08} ${cardX + cardW * 0.7} ${cardY + cardH * 0.24}`,
      class: "fig-highlight",
    }));
    svg.append(element("rect", {
      x: cardX + cardW * 0.24,
      y: cardY + cardH * 0.56,
      width: cardW * 0.5,
      height: Math.max(3, cardH * 0.055),
      rx: 3,
      class: "fig-typography",
    }));
  }

  if (options.variant === "correct" || options.variant === "wrong") {
    const marks: Array<[number, string]> = options.variant === "correct"
      ? [[boundaries[0], "fig-mark fig-mark--rim"], [boundaries[1], "fig-mark fig-mark--shoulder"], [boundaries[2], "fig-mark fig-mark--center"]]
      : [[-0.05, "fig-mark fig-mark--bad"], [boundaries[1] * 0.35, "fig-mark fig-mark--bad"], [boundaries[2] * 1.9, "fig-mark fig-mark--bad"]];
    for (const [ratio, className] of marks) {
      const pad = ratio * inset;
      svg.append(element("rect", {
        x: cardX + pad,
        y: cardY + pad,
        width: Math.max(2, cardW - pad * 2),
        height: Math.max(2, cardH - pad * 2),
        rx: Math.max(2, 20 - pad * 0.5),
        class: className,
      }));
    }
  }

  if (labelled) {
    // Labels are spread evenly down the gutter and connected to the middle of
    // the band they name, so four thin bands stay readable.
    const labelX = cardX + cardW + 30;
    const midpoints = [
      boundaries[0] / 2,
      (boundaries[0] + boundaries[1]) / 2,
      (boundaries[1] + boundaries[2]) / 2,
    ];
    const rows: Array<[string, string, number]> = [
      [t("zoneSidewall"), "fig-key fig-key--sidewall", cardX + cardW - midpoints[0] * inset],
      [t("zoneRim"), "fig-key fig-key--rim", cardX + cardW - midpoints[1] * inset],
      [t("zoneShoulder"), "fig-key fig-key--shoulder", cardX + cardW - midpoints[2] * inset],
      [t("zoneCenter"), "fig-key fig-key--center", cardX + cardW * 0.5],
    ];
    const top = cardY + cardH * 0.16;
    const spacing = (cardH * 0.68) / (rows.length - 1);
    rows.forEach(([label, className, anchorX], index) => {
      const y = top + spacing * index;
      const anchorY = index === rows.length - 1 ? cardY + cardH / 2 : cardY + midpoints[index] * inset;
      svg.append(element("line", { x1: anchorX, y1: anchorY, x2: labelX - 8, y2: y - 4, class: "fig-leader" }));
      svg.append(element("circle", { cx: anchorX, cy: anchorY, r: 2.5, class: className.replace("fig-key", "fig-anchor") }));
      svg.append(element("text", { x: labelX, y, class: className }, label));
    });
  }
  return svg;
}

function figureCard(title: string, node: Node, caption: string, tone?: "good" | "bad"): HTMLElement {
  const wrapper = document.createElement("figure");
  wrapper.className = "rv-figure-card";
  if (tone) wrapper.dataset.tone = tone;
  const heading = document.createElement("h4");
  heading.textContent = title;
  const description = document.createElement("figcaption");
  description.textContent = caption;
  wrapper.append(heading, node, description);
  return wrapper;
}

const NOT_A_BOUNDARY: Array<{ key: Parameters<typeof t>[0]; draw: (svg: SVGSVGElement) => void }> = [
  {
    key: "notHighlight",
    draw: (svg) => svg.append(element("path", { d: "M 18 44 Q 60 20 104 42", class: "fig-highlight fig-strong" })),
  },
  {
    key: "notHalo",
    draw: (svg) => svg.append(element("rect", { x: 8, y: 10, width: 106, height: 58, rx: 16, class: "fig-halo fig-strong" })),
  },
  {
    key: "notDispersion",
    draw: (svg) => {
      svg.append(element("rect", { x: 14, y: 16, width: 94, height: 46, rx: 10, class: "fig-dispersion-outer" }));
      svg.append(element("rect", { x: 19, y: 21, width: 84, height: 36, rx: 8, class: "fig-dispersion-inner" }));
    },
  },
  {
    key: "notTypography",
    draw: (svg) => svg.append(element("rect", { x: 34, y: 34, width: 54, height: 10, rx: 3, class: "fig-typography fig-strong" })),
  },
  {
    key: "notInnerBorder",
    draw: (svg) => svg.append(element("rect", { x: 30, y: 26, width: 62, height: 26, rx: 4, class: "fig-inner-border" })),
  },
  {
    key: "notNeighbour",
    draw: (svg) => {
      svg.append(element("rect", { x: 12, y: 18, width: 52, height: 42, rx: 9, class: "fig-center" }));
      svg.append(element("rect", { x: 72, y: 18, width: 46, height: 42, rx: 9, class: "fig-neighbour" }));
    },
  },
];

function miniFigure(index: number): SVGSVGElement {
  const svg = element("svg", { viewBox: "0 0 124 78", class: "rv-mini-figure", "aria-hidden": "true" });
  svg.append(element("rect", { x: 14, y: 16, width: 94, height: 46, rx: 10, class: "fig-card-base" }));
  NOT_A_BOUNDARY[index].draw(svg);
  svg.append(element("line", { x1: 14, y1: 70, x2: 108, y2: 70, class: "fig-strike" }));
  return svg;
}

export interface TutorialOptions {
  /** A rectified crop of a real Frozen target card, produced by the caller. */
  realCard: HTMLCanvasElement | null;
  onStart: () => void;
}

export function renderTutorial(options: TutorialOptions): HTMLElement {
  const root = document.createElement("section");
  root.className = "rv-tutorial";
  root.innerHTML = `
    <header class="rv-tutorial-head">
      <span class="rv-chip">${t("tutorialBadge")}</span>
      <h1>${t("tutorialTitle")}</h1>
      <p>${t("tutorialNoWrite")}</p>
    </header>
  `;

  const grid = document.createElement("div");
  grid.className = "rv-tutorial-grid";

  const schematic = syntheticCard({ labels: true, width: 460, height: 280 });
  grid.append(figureCard(t("tutorialSynthetic"), schematic, `${t("tutorialOutline")}：${t("tutorialOutlineHelp")}`));

  if (options.realCard) {
    grid.append(figureCard(t("tutorialReal"), options.realCard, t("zoneShoulderHelp")));
  }

  const zones = document.createElement("dl");
  zones.className = "rv-zone-legend";
  const entries: Array<[string, string, string]> = [
    ["center", t("zoneCenter"), t("zoneCenterHelp")],
    ["shoulder", t("zoneShoulder"), t("zoneShoulderHelp")],
    ["rim", t("zoneRim"), t("zoneRimHelp")],
    ["sidewall", t("zoneSidewall"), t("zoneSidewallHelp")],
  ];
  for (const [key, term, detail] of entries) {
    const row = document.createElement("div");
    row.dataset.zone = key;
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = detail;
    row.append(dt, dd);
    zones.append(row);
  }
  grid.append(figureCard(t("summaryZones"), zones, t("dragHint")));

  const comparison = document.createElement("div");
  comparison.className = "rv-compare-figures";
  comparison.append(
    figureCard(t("exampleCorrect"), syntheticCard({ variant: "correct", width: 300, height: 200 }), t("zoneRimHelp"), "good"),
    figureCard(t("exampleWrong"), syntheticCard({ variant: "wrong", width: 300, height: 200 }), t("notHalo"), "bad"),
  );
  grid.append(comparison);

  const forbidden = document.createElement("section");
  forbidden.className = "rv-forbidden";
  const forbiddenTitle = document.createElement("h3");
  forbiddenTitle.textContent = t("tutorialNotBoundary");
  forbidden.append(forbiddenTitle);
  const list = document.createElement("ul");
  NOT_A_BOUNDARY.forEach((entry, index) => {
    const item = document.createElement("li");
    item.append(miniFigure(index));
    const label = document.createElement("span");
    label.textContent = t(entry.key);
    item.append(label);
    list.append(item);
  });
  forbidden.append(list);
  grid.append(forbidden);

  root.append(grid);

  const actions = document.createElement("div");
  actions.className = "rv-actions";
  const start = document.createElement("button");
  start.type = "button";
  start.className = "rv-primary";
  start.id = "rv-tutorial-start";
  start.textContent = t("tutorialStart");
  start.addEventListener("click", options.onStart);
  actions.append(start);
  root.append(actions);
  return root;
}
