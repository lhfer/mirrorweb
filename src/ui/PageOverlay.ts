/**
 * The page chrome: the bottom scrim and the footer that sits on it.
 *
 * The Target's own chrome is one fixed, full-width, bottom-anchored container
 * holding two things (read from its live DOM, `artifacts/visual-convergence/
 * recon.json`): a 144 px gradient scrim across the whole width, and a row that
 * is bottom-aligned on desktop and centred on a phone. The scrim sits ABOVE
 * the cards and their labels, so it grounds the bottom of the page rather than
 * tinting a background nobody can see.
 *
 * We had the row and not the scrim. On matched media and matched copy the
 * bottom 144 rows of our page read 13 to 19 luma levels brighter than the
 * Target's at the four review viewports, and up to 43 levels brighter at the
 * last screen row (`qa-v5/visual-convergence/p0-decision.json`).
 *
 * The wordmark is ours, not the Target's -- its logo is its own studio mark
 * and is never copied here. What is matched is the PRESENTATION: a box of
 * width `min(26vw, 148px)` carrying a drop shadow, so the mark scales with the
 * viewport the way the Target's does instead of staying 132 px wide on a
 * phone. Inline SVG rather than an image, because the mark is type and inline
 * SVG uses the page's own loaded face.
 */
const WORDMARK = `
  <span class="footer-wordmark" role="img" aria-label="ATELIER">
    <svg viewBox="0 0 265 35.5" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="ilg-wordmark-mark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ff3b30" />
          <stop offset="16%" stop-color="#ff9500" />
          <stop offset="33%" stop-color="#ffcc00" />
          <stop offset="50%" stop-color="#34c759" />
          <stop offset="66%" stop-color="#007aff" />
          <stop offset="83%" stop-color="#5856d6" />
          <stop offset="100%" stop-color="#af52de" />
        </linearGradient>
      </defs>
      <rect x="0" y="3.75" width="56" height="28" rx="14" fill="url(#ilg-wordmark-mark)" />
      <text class="footer-wordmark-text" x="76" y="31.75"
            textLength="189" lengthAdjust="spacing">ATELIER</text>
    </svg>
  </span>`;

export class PageOverlay {
  constructor(host: HTMLElement) {
    host.innerHTML = `
      <div class="page-chrome-scrim" aria-hidden="true"></div>
      <footer class="page-footer">
        <a class="experiment-link" href="https://shader.se/" target="_blank" rel="noreferrer">
          <span class="experiment-caption">AN EXPERIMENT BY</span>
          ${WORDMARK}
        </a>
        <a class="cta-link" href="https://cal.com/simon-hedlund-kglzne" target="_blank" rel="noreferrer">
          <span class="cta-sheen" aria-hidden="true"></span>
          <span class="cta-label">Book a Call</span>
          <span class="cta-arrow">↗</span>
        </a>
      </footer>
    `;
  }
}
