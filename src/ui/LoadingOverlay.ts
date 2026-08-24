import ENTRY from "../../config/target-entry-source-v1.json";
import { getContentManifest } from "../content/ContentRepository";
import { Spring } from "../interaction/SourceExactMotion";

const PROGRESS = ENTRY.progress;
const EXIT = ENTRY.loader.exit;
const CONTENT_BOOT_PERCENT = 3;

type LoaderDom = {
  brandEl: HTMLElement;
  percentEl: HTMLElement;
};

function buildLoaderDom(host: HTMLElement, brandText: string): LoaderDom {
  const cluster = document.createElement("div");
  cluster.className = "loader-cluster";
  const brand = document.createElement("div");
  brand.className = "loader-brand";
  const mark = document.createElement("div");
  mark.className = "brand-mark";
  mark.setAttribute("aria-hidden", "true");
  const brandWord = document.createElement("p");
  brandWord.className = "brand-word";
  brandWord.textContent = brandText;
  brand.append(mark, brandWord);
  const percent = document.createElement("p");
  percent.className = "loader-percent";
  percent.textContent = "0%";
  cluster.append(brand, percent);
  host.replaceChildren(cluster);
  return { brandEl: brandWord, percentEl: percent };
}

function configureProgressbar(host: HTMLElement, sourceExact: boolean): void {
  host.classList.toggle("is-source-exact", sourceExact);
  if (sourceExact) {
    host.setAttribute("role", "progressbar");
    host.setAttribute("aria-valuemin", "0");
    host.setAttribute("aria-valuemax", "100");
  } else {
    host.removeAttribute("role");
    host.removeAttribute("aria-valuemin");
    host.removeAttribute("aria-valuemax");
    host.removeAttribute("aria-valuenow");
  }
}

/**
 * Makes the manifest request visible without constructing the renderer app.
 * The app's LoadingOverlay takes over the same host at 3%, the first existing
 * source-exact asset milestone, so the accepted video/compile ladder remains.
 */
export function mountContentBootLoader(host: HTMLElement, sourceExact: boolean) {
  configureProgressbar(host, sourceExact);
  const dom = buildLoaderDom(host, getContentManifest().site.loaderBrandText);
  const setProgress = (fraction: number) => {
    const percent = Math.round(Math.max(0, Math.min(1, fraction)) * CONTENT_BOOT_PERCENT);
    host.dataset.contentBootProgress = String(percent);
    dom.percentEl.textContent = `${percent}%`;
    if (sourceExact) host.setAttribute("aria-valuenow", String(percent));
  };
  setProgress(0);
  return Object.freeze({
    setProgress,
    setBrandText(value: string) {
      dom.brandEl.textContent = value;
    },
  });
}

/**
 * The loading overlay keeps the accepted v1.0 spring, monotonic progress and
 * exit timing. Manifest loading merely occupies the existing first 3%.
 */
export class LoadingOverlay {
  private readonly root: HTMLElement;
  private readonly percentEl: HTMLElement;
  private readonly sourceExact: boolean;
  private readonly spring: Spring | null;
  private value = 0;
  private shown = -1;
  private raf = 0;
  private hidden = false;

  constructor(host: HTMLElement, sourceExact = false) {
    this.root = host;
    this.sourceExact = sourceExact;
    const initial = Math.max(
      0,
      Math.min(100, Number(host.dataset.contentBootProgress) || 0),
    );
    const dom = buildLoaderDom(host, getContentManifest().site.loaderBrandText);
    this.percentEl = dom.percentEl;
    configureProgressbar(host, sourceExact);
    this.value = initial;
    if (sourceExact) {
      this.spring = new Spring({
        stiffness: PROGRESS.displaySpring.stiffness,
        damping: PROGRESS.displaySpring.damping,
        mass: PROGRESS.displaySpring.mass,
        restDelta: PROGRESS.displaySpring.restDelta,
        restSpeed: PROGRESS.displaySpring.restSpeed,
      }, initial);
      this.paint(Math.round(initial));
      this.tick(performance.now());
    } else {
      this.spring = null;
      this.paint(Math.round(initial));
    }
  }

  setPercent(value: number): void {
    const clamped = Math.max(0, Math.min(100, value));
    if (clamped <= this.value && this.sourceExact) return;
    this.value = Math.max(this.value, clamped);
    if (!this.spring) {
      this.paint(Math.round(this.value));
      return;
    }
    this.spring.setTarget(this.value, performance.now());
  }

  private paint(rounded: number): void {
    if (rounded === this.shown) return;
    this.shown = rounded;
    this.percentEl.textContent = `${rounded}%`;
    if (this.sourceExact) this.root.setAttribute("aria-valuenow", String(rounded));
  }

  private tick = (now: number) => {
    if (this.hidden || !this.spring) return;
    this.spring.advance(now);
    this.paint(Math.round(this.spring.value));
    this.raf = requestAnimationFrame(this.tick);
  };

  /** The last percentage a viewer actually saw. QA and evidence only. */
  displayedPercent(): number {
    return this.shown;
  }

  hide(): void {
    if (this.hidden) return;
    this.hidden = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    if (!this.sourceExact) this.setPercent(100);
    this.root.classList.add("is-hidden");
    window.setTimeout(() => {
      this.root.style.display = "none";
    }, this.sourceExact ? EXIT.durationMs : 480);
  }
}
