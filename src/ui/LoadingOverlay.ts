export class LoadingOverlay {
  private readonly root: HTMLElement;
  private readonly percentEl: HTMLElement;

  constructor(host: HTMLElement) {
    this.root = host;
    host.innerHTML = `
      <div class="loader-cluster">
        <div class="loader-brand">
          <div class="brand-mark" aria-hidden="true"></div>
          <p class="brand-word">ATELIER</p>
        </div>
        <p class="loader-percent">0%</p>
      </div>
    `;
    this.percentEl = host.querySelector(".loader-percent") as HTMLElement;
  }

  setPercent(value: number) {
    const rounded = Math.max(0, Math.min(100, Math.round(value)));
    this.percentEl.textContent = `${rounded}%`;
  }

  hide() {
    this.setPercent(100);
    this.root.classList.add("is-hidden");
    window.setTimeout(() => {
      this.root.style.display = "none";
    }, 480);
  }
}
