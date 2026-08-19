export class PageOverlay {
  constructor(host: HTMLElement) {
    host.innerHTML = `
      <footer class="page-footer">
        <a class="experiment-link" href="https://shader.se/" target="_blank" rel="noreferrer">
          <span>AN EXPERIMENT BY</span>
          <span class="loader-brand">
            <span class="brand-mark" aria-hidden="true"></span>
            <span class="brand-word">ATELIER</span>
          </span>
        </a>
        <a class="cta-link" href="https://cal.com/simon-hedlund-kglzne" target="_blank" rel="noreferrer">
          Book a Call
          <span class="cta-arrow">↗</span>
        </a>
      </footer>
    `;
  }
}
