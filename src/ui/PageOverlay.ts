import { getContentManifest } from "../content/ContentRepository";

const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement<K extends keyof SVGElementTagNameMap>(name: K): SVGElementTagNameMap[K] {
  return document.createElementNS(SVG_NS, name);
}

/**
 * The page chrome remains the accepted v1.0 tree and classes. Only its text
 * nodes and safe links now come from the once-installed content manifest.
 */
export class PageOverlay {
  constructor(host: HTMLElement) {
    const { site } = getContentManifest();

    const scrim = document.createElement("div");
    scrim.className = "page-chrome-scrim";
    scrim.setAttribute("aria-hidden", "true");

    const footer = document.createElement("footer");
    footer.className = "page-footer";

    const experimentLink = document.createElement("a");
    experimentLink.className = "experiment-link";
    experimentLink.href = site.brandUrl;
    experimentLink.target = "_blank";
    experimentLink.rel = "noreferrer";
    const caption = document.createElement("span");
    caption.className = "experiment-caption";
    caption.textContent = site.footerCaption;

    const wordmark = document.createElement("span");
    wordmark.className = "footer-wordmark";
    wordmark.setAttribute("role", "img");
    wordmark.setAttribute("aria-label", site.brandText);
    const svg = svgElement("svg");
    svg.setAttribute("viewBox", "0 0 265 35.5");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const defs = svgElement("defs");
    const gradient = svgElement("linearGradient");
    gradient.id = "ilg-wordmark-mark";
    gradient.setAttribute("x1", "0");
    gradient.setAttribute("y1", "0");
    gradient.setAttribute("x2", "0");
    gradient.setAttribute("y2", "1");
    const stops: readonly [string, string][] = [
      ["0%", "#ff3b30"],
      ["16%", "#ff9500"],
      ["33%", "#ffcc00"],
      ["50%", "#34c759"],
      ["66%", "#007aff"],
      ["83%", "#5856d6"],
      ["100%", "#af52de"],
    ];
    for (const [offset, colour] of stops) {
      const stop = svgElement("stop");
      stop.setAttribute("offset", offset);
      stop.setAttribute("stop-color", colour);
      gradient.appendChild(stop);
    }
    defs.appendChild(gradient);
    const mark = svgElement("rect");
    mark.setAttribute("x", "0");
    mark.setAttribute("y", "3.75");
    mark.setAttribute("width", "56");
    mark.setAttribute("height", "28");
    mark.setAttribute("rx", "14");
    mark.setAttribute("fill", "url(#ilg-wordmark-mark)");
    const text = svgElement("text");
    text.classList.add("footer-wordmark-text");
    text.setAttribute("x", "76");
    text.setAttribute("y", "31.75");
    text.setAttribute("textLength", "189");
    text.setAttribute("lengthAdjust", "spacing");
    text.textContent = site.brandText;
    svg.append(defs, mark, text);
    wordmark.appendChild(svg);
    experimentLink.append(caption, wordmark);

    const cta = document.createElement("a");
    cta.className = "cta-link";
    cta.href = site.ctaUrl;
    cta.target = "_blank";
    cta.rel = "noreferrer";
    const sheen = document.createElement("span");
    sheen.className = "cta-sheen";
    sheen.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "cta-label";
    label.textContent = site.ctaLabel;
    const arrow = document.createElement("span");
    arrow.className = "cta-arrow";
    arrow.textContent = "↗";
    cta.append(sheen, label, arrow);

    footer.append(experimentLink, cta);
    host.replaceChildren(scrim, footer);
  }
}
