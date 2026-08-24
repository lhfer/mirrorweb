import { computeMediaFit } from "../content/MediaFit";
import { TARGET_GRID } from "../layout/SourceExactLayout";
import {
  AdapterError,
  cloneManifest,
  CONTENT_LIMITS,
  formatBytes,
  formatDuration,
  sortCards,
  validateManifest,
  type AdminAdapter,
  type AdminActor,
  type ContentCard,
  type ContentManifest,
  type ContentVersion,
  type MediaAsset,
  type PreparedMedia,
  type UploadProgress,
  type WorkspaceSnapshot,
} from "./domain";
import { prepareMedia } from "./media";

type Page = "cards" | "media" | "settings" | "history" | "preview";
type CardFilter = "all" | "enabled" | "disabled";
type SaveState = "clean" | "dirty" | "saving" | "conflict" | "invalid" | "error";
type PreviewMode = "draft" | "published";
type PreviewPreset = "desktop" | "portrait" | "landscape";

type RemovedCard = { card: ContentCard; index: number };

type UploadJob = {
  file: File;
  progress: UploadProgress;
  message: string;
  controller: AbortController;
  error?: string;
};

type Child = Node | string | number | false | null | undefined;

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children) {
    if (child === false || child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function iconButton(label: string, glyph: string, onClick: () => void): HTMLButtonElement {
  const button = element("button", "icon-button", glyph);
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.title = label;
  button.addEventListener("click", onClick);
  return button;
}

function textButton(
  label: string,
  className: string,
  onClick: () => void,
): HTMLButtonElement {
  const button = element("button", className, label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

function field(labelText: string, control: HTMLElement, hint?: string): HTMLLabelElement {
  const label = element("label", "field");
  label.append(element("span", "field-label", labelText), control);
  if (hint) label.append(element("span", "field-hint", hint));
  return label;
}

function textInput(
  value: string,
  onInput: (value: string) => void,
  options: { maxLength?: number; placeholder?: string; type?: string } = {},
): HTMLInputElement {
  const input = element("input", "text-input");
  input.type = options.type ?? "text";
  input.value = value;
  if (options.maxLength) input.maxLength = options.maxLength;
  if (options.placeholder) input.placeholder = options.placeholder;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function textArea(
  value: string,
  onInput: (value: string) => void,
  maxLength: number,
): HTMLTextAreaElement {
  const area = element("textarea", "text-area");
  area.value = value;
  area.maxLength = maxLength;
  area.rows = 4;
  area.addEventListener("input", () => onInput(area.value));
  return area;
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "—"
    : new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function cardsEqual(a: ContentCard | undefined, b: ContentCard | undefined): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export class AdminApp {
  private workspace?: WorkspaceSnapshot;
  private manifest?: ContentManifest;
  private savedManifest?: ContentManifest;
  private actor?: AdminActor;
  private page: Page = "cards";
  private selectedCardId?: string;
  private cardSearch = "";
  private cardFilter: CardFilter = "all";
  private saveState: SaveState = "clean";
  private saveMessage = "已同步";
  private saveTimer?: number;
  private editSerial = 0;
  private conflictMessage?: string;
  private removedCard?: RemovedCard;
  private dragCardId?: string;
  private uploadJob?: UploadJob;
  private retryFile?: File;
  private previewMode: PreviewMode = "draft";
  private previewPreset: PreviewPreset = "desktop";
  private authUnsubscribe?: () => void;
  private authRefreshPending = false;
  private toastTimer?: number;

  constructor(
    private readonly root: HTMLElement,
    private readonly adapter: AdminAdapter,
  ) {}

  async start(): Promise<void> {
    this.renderBoot();
    this.authUnsubscribe = this.adapter.onAuthChange(() => {
      if (!this.authRefreshPending) void this.refreshAuth();
    });
    await this.refreshAuth();
  }

  destroy(): void {
    this.authUnsubscribe?.();
    if (this.saveTimer) window.clearTimeout(this.saveTimer);
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    this.uploadJob?.controller.abort();
  }

  private async refreshAuth(): Promise<void> {
    this.authRefreshPending = true;
    try {
      const state = await this.adapter.getAuthState();
      if (state.kind === "anonymous") {
        this.actor = undefined;
        this.renderLogin();
        return;
      }
      if (state.kind === "forbidden") {
        this.actor = undefined;
        this.renderForbidden(state.email);
        return;
      }
      this.actor = state.actor;
      await this.loadWorkspace();
    } catch (error) {
      this.renderFatal(this.errorMessage(error));
    } finally {
      this.authRefreshPending = false;
    }
  }

  private async loadWorkspace(): Promise<void> {
    this.renderBoot("正在读取草稿、媒体和版本历史");
    this.workspace = await this.adapter.loadWorkspace();
    this.manifest = cloneManifest(this.workspace.draft.manifest);
    this.savedManifest = cloneManifest(this.workspace.draft.manifest);
    this.selectedCardId = this.manifest.cards[0]?.id;
    this.saveState = "clean";
    this.saveMessage = "已同步";
    this.conflictMessage = undefined;
    this.persistPreviewDraft();
    this.renderShell();
  }

  private renderBoot(message = "正在验证管理员会话"): void {
    const mark = element("div", "boot-mark", "MW");
    const copy = element(
      "div",
      "boot-copy",
      element("p", "eyebrow", "MIRRORWEB / CONTENT DESK"),
      element("h1", "boot-title", "编辑后台正在就绪"),
      element("p", "muted", message),
    );
    const pulse = element("span", "boot-pulse");
    this.root.replaceChildren(element("section", "boot-screen", mark, copy, pulse));
  }

  private renderLogin(): void {
    const email = textInput("", () => undefined, { type: "email", placeholder: "admin@example.com" });
    email.required = true;
    email.autocomplete = "email";
    const status = element("p", "auth-status", "仅预先批准的管理员邮箱可以进入。");
    const submit = textButton("发送 Magic Link", "button button-accent", () => undefined);
    const form = element(
      "form",
      "auth-form",
      field("管理员邮箱", email),
      submit,
      status,
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      status.textContent = "正在发送…";
      try {
        await this.adapter.sendMagicLink(email.value.trim());
        status.textContent = "Magic Link 已发送。请在同一浏览器中打开邮件链接。";
      } catch (error) {
        status.textContent = this.errorMessage(error);
      } finally {
        submit.disabled = false;
      }
    });

    this.root.replaceChildren(
      element(
        "section",
        "auth-screen",
        element(
          "div",
          "auth-intro",
          element("p", "eyebrow", "MIRRORWEB / RESTRICTED"),
          element("h1", "auth-title", "内容进入发布前，先确认你是谁。"),
          element("p", "auth-lede", "Magic Link 登录，不创建新用户，不在浏览器保存管理员密码。"),
        ),
        element(
          "div",
          "auth-panel",
          element("div", "auth-index", "01 / AUTH"),
          form,
        ),
      ),
    );
    queueMicrotask(() => email.focus());
  }

  private renderForbidden(email: string): void {
    const logout = textButton("退出此账号", "button button-quiet", async () => {
      await this.adapter.signOut();
      await this.refreshAuth();
    });
    this.root.replaceChildren(
      element(
        "section",
        "status-screen",
        element("div", "status-code", "403"),
        element(
          "div",
          "status-copy",
          element("p", "eyebrow", "AUTHENTICATED / NOT AUTHORIZED"),
          element("h1", "status-title", "这个账号不在管理员白名单中。"),
          element("p", "muted", email),
          logout,
        ),
      ),
    );
  }

  private renderFatal(message: string): void {
    const retry = textButton("重新连接", "button button-accent", () => void this.refreshAuth());
    this.root.replaceChildren(
      element(
        "section",
        "status-screen",
        element("div", "status-code", "ERR"),
        element(
          "div",
          "status-copy",
          element("p", "eyebrow", "CONTENT DESK / BOOT FAILURE"),
          element("h1", "status-title", "后台没有完成启动。"),
          element("p", "muted", message),
          retry,
        ),
      ),
    );
  }

  private renderShell(): void {
    if (!this.workspace || !this.manifest || !this.actor) return;
    const shell = element("div", "admin-shell");
    shell.append(this.renderHeader(), this.renderRail());
    const work = element("main", "workspace");
    work.id = "workspace";
    work.tabIndex = -1;
    work.append(this.renderCurrentPage());
    if (this.conflictMessage) work.prepend(this.renderConflict());
    shell.append(work, element("div", "toast-region"));
    this.root.replaceChildren(shell);
    this.updateSaveReadout();
  }

  private renderHeader(): HTMLElement {
    const brand = element(
      "div",
      "desk-brand",
      element("span", "desk-monogram", "MW"),
      element(
        "div",
        "desk-name",
        element("strong", "", "Content Desk"),
        element("span", "", "MirrorWeb editorial control"),
      ),
    );
    const environment = element(
      "span",
      `environment-badge ${this.adapter.mode === "local" ? "is-local" : "is-live"}`,
      this.adapter.mode === "local" ? "LOCAL SANDBOX" : "SUPABASE LIVE",
    );
    const save = element(
      "div",
      "save-readout",
      element("span", "save-dot"),
      element("span", "save-label", this.saveMessage),
      element("span", "revision-label", `r${this.workspace?.draft.revision ?? 0}`),
    );
    save.id = "save-readout";

    const manualSave = textButton("保存", "button button-quiet compact", () => void this.saveNow(true));
    manualSave.id = "manual-save";
    const preview = textButton("预览草稿", "button button-quiet compact", () => this.navigate("preview"));
    const publish = textButton("发布", "button button-accent compact", () => this.openPublishDialog());
    const logout = iconButton("退出登录", "↪", async () => {
      await this.adapter.signOut();
      await this.refreshAuth();
    });
    if (this.adapter.mode === "local") {
      logout.disabled = true;
      logout.title = "LOCAL SANDBOX 没有远程会话";
    }
    const actor = element(
      "div",
      "actor",
      element("span", "actor-mark", this.actor?.email.slice(0, 1).toLocaleUpperCase() ?? "A"),
      element("span", "actor-email", this.actor?.email ?? "—"),
    );

    return element(
      "header",
      "topbar",
      brand,
      element("div", "topbar-context", environment, save),
      element("div", "topbar-actions", manualSave, preview, publish, actor, logout),
    );
  }

  private renderRail(): HTMLElement {
    const nav = element("nav", "rail-nav");
    nav.setAttribute("aria-label", "后台导航");
    const entries: Array<[Page, string, string]> = [
      ["cards", "01", "Cards"],
      ["media", "02", "Media Library"],
      ["settings", "03", "Site Settings"],
      ["history", "04", "Publish History"],
      ["preview", "05", "Draft Preview"],
    ];
    for (const [page, number, label] of entries) {
      const button = element(
        "button",
        `rail-link${page === this.page ? " is-active" : ""}`,
        element("span", "rail-number", number),
        element("span", "rail-label", label),
      );
      button.type = "button";
      if (page === this.page) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => this.navigate(page));
      nav.append(button);
    }

    const stats = element(
      "div",
      "rail-stats",
      element("span", "rail-stat-label", "DRAFT"),
      element("strong", "rail-stat-value", `${this.manifest?.cards.length ?? 0} cards`),
      element("span", "rail-stat-note", `${this.manifest?.cards.filter((card) => card.enabled).length ?? 0} enabled`),
    );
    const privacy = element(
      "p",
      "rail-footnote",
      this.adapter.mode === "local"
        ? "本地模拟数据。不会发布到公共站点。"
        : "上传内容位于 public-read bucket；请仅上传可公开媒体。",
    );
    return element("aside", "side-rail", nav, stats, privacy);
  }

  private navigate(page: Page): void {
    this.page = page;
    this.renderShell();
    window.scrollTo({ top: 0, behavior: "auto" });
    queueMicrotask(() => document.querySelector<HTMLElement>("#workspace")?.focus({ preventScroll: true }));
  }

  private renderCurrentPage(): HTMLElement {
    switch (this.page) {
      case "media": return this.renderMediaPage();
      case "settings": return this.renderSettingsPage();
      case "history": return this.renderHistoryPage();
      case "preview": return this.renderPreviewPage();
      default: return this.renderCardsPage();
    }
  }

  private renderPageOnly(): void {
    const workspace = this.root.querySelector<HTMLElement>("#workspace");
    if (!workspace) return this.renderShell();
    workspace.replaceChildren(this.renderCurrentPage());
    if (this.conflictMessage) workspace.prepend(this.renderConflict());
    this.updateSaveReadout();
    this.updateRailStats();
  }

  private pageHeading(kicker: string, title: string, detail: string): HTMLElement {
    return element(
      "header",
      "page-heading",
      element("div", "heading-index", kicker),
      element(
        "div",
        "heading-copy",
        element("h1", "page-title", title),
        element("p", "page-detail", detail),
      ),
    );
  }

  private renderCardsPage(): HTMLElement {
    const page = element("section", "page page-cards");
    page.append(this.pageHeading("01 / CATALOG", "Cards", "编辑内容、媒体绑定与确定性的发布顺序。"));

    const search = textInput(this.cardSearch, (value) => {
      this.cardSearch = value;
      const position = search.selectionStart ?? value.length;
      this.renderPageOnly();
      const next = this.root.querySelector<HTMLInputElement>("#card-search");
      next?.focus();
      next?.setSelectionRange(position, position);
    }, { placeholder: "搜索 code / title / category" });
    search.id = "card-search";
    search.setAttribute("aria-label", "搜索卡片");
    const filter = element("select", "select-input");
    filter.setAttribute("aria-label", "筛选启用状态");
    for (const [value, label] of [["all", "全部"], ["enabled", "已启用"], ["disabled", "已停用"]] as const) {
      const option = element("option", "", label);
      option.value = value;
      option.selected = value === this.cardFilter;
      filter.append(option);
    }
    filter.addEventListener("change", () => {
      this.cardFilter = filter.value as CardFilter;
      this.renderPageOnly();
    });
    const create = textButton("＋ 新建卡片", "button button-accent", () => this.createCard());
    const toolbar = element("div", "catalog-toolbar", search, filter, create);

    const cards = this.filteredCards();
    const list = element("div", "catalog-list");
    const listMeta = element(
      "div",
      "list-meta",
      element("span", "", `${cards.length} / ${this.manifest?.cards.length ?? 0}`),
      element("span", "", "拖动或在手柄上使用 ↑ ↓"),
    );
    const rows = element("ol", "card-rows");
    rows.setAttribute("aria-label", "卡片排序列表");
    for (const card of cards) rows.append(this.renderCardRow(card));
    if (!cards.length) rows.append(element("li", "empty-row", "没有符合筛选条件的卡片。"));
    list.append(listMeta, rows);

    const editor = this.renderCardEditor();
    page.append(toolbar, element("div", "catalog-workbench", list, editor));
    return page;
  }

  private filteredCards(): ContentCard[] {
    if (!this.manifest) return [];
    const query = this.cardSearch.trim().toLocaleLowerCase();
    return sortCards(this.manifest.cards).filter((card) => {
      const status = this.cardFilter === "all"
        || (this.cardFilter === "enabled" && card.enabled)
        || (this.cardFilter === "disabled" && !card.enabled);
      const match = !query || [card.code, card.category, card.title, card.deck]
        .some((value) => value.toLocaleLowerCase().includes(query));
      return status && match;
    });
  }

  private renderCardRow(card: ContentCard): HTMLLIElement {
    const row = element("li", `card-row${card.id === this.selectedCardId ? " is-selected" : ""}`);
    row.draggable = true;
    row.dataset.cardId = card.id;
    const handle = element("button", "drag-handle", "⋮⋮");
    handle.type = "button";
    handle.setAttribute("aria-label", `调整 ${card.title} 的顺序`);
    handle.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      this.moveCard(card.id, event.key === "ArrowUp" ? -1 : 1);
    });
    const index = element("span", "card-order", String(card.sortOrder + 1).padStart(2, "0"));
    const accent = element("span", "card-accent");
    accent.style.backgroundColor = card.accent;
    const copy = element(
      "button",
      "card-row-main",
      element("span", "card-row-code", card.code),
      element("strong", "card-row-title", card.title),
      element("span", "card-row-category", card.category),
    );
    copy.type = "button";
    copy.addEventListener("click", () => {
      this.selectedCardId = card.id;
      this.renderPageOnly();
    });
    const status = element("span", `status-pill ${card.enabled ? "is-ready" : "is-muted"}`, card.enabled ? "LIVE" : "OFF");
    row.append(handle, index, accent, copy, status);
    row.addEventListener("dragstart", (event) => {
      this.dragCardId = card.id;
      event.dataTransfer?.setData("text/plain", card.id);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
      row.classList.add("is-dragging");
    });
    row.addEventListener("dragend", () => {
      this.dragCardId = undefined;
      row.classList.remove("is-dragging");
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
      row.classList.add("is-drop-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("is-drop-target"));
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      row.classList.remove("is-drop-target");
      const source = this.dragCardId ?? event.dataTransfer?.getData("text/plain");
      if (source) this.reorderCard(source, card.id);
    });
    return row;
  }

  private renderCardEditor(): HTMLElement {
    const card = this.currentCard();
    if (!card) {
      return element(
        "aside",
        "card-editor empty-editor",
        element("span", "editor-index", "NO SELECTION"),
        element("p", "", "从左侧选择一张卡片开始编辑。"),
      );
    }

    const duplicate = textButton("复制", "button button-quiet compact", () => this.duplicateCard(card));
    const remove = textButton("移除", "button button-danger compact", () => this.removeCard(card));
    const heading = element(
      "header",
      "editor-heading",
      element(
        "div",
        "",
        element("span", "editor-index", `CARD / ${String(card.sortOrder + 1).padStart(2, "0")}`),
        element("h2", "editor-title", card.title),
      ),
      element("div", "editor-actions", duplicate, remove),
    );

    const code = textInput(card.code, (value) => this.editCard(card, "code", value), { maxLength: CONTENT_LIMITS.code });
    const category = textInput(card.category, (value) => this.editCard(card, "category", value), { maxLength: CONTENT_LIMITS.category });
    const title = textInput(card.title, (value) => {
      this.editCard(card, "title", value);
      const liveTitle = this.root.querySelector<HTMLElement>(".editor-title");
      if (liveTitle) liveTitle.textContent = value || "Untitled";
    }, { maxLength: CONTENT_LIMITS.title });
    const deck = textArea(card.deck, (value) => this.editCard(card, "deck", value), CONTENT_LIMITS.deck);

    const identity = element(
      "div",
      "editor-section",
      element("h3", "section-title", "01 · Editorial identity"),
      element("div", "field-grid two", field("Code", code), field("Category", category)),
      field("Title", title, `${card.title.length} / ${CONTENT_LIMITS.title}`),
      field("Deck", deck, `${card.deck.length} / ${CONTENT_LIMITS.deck}`),
    );

    const palette = element("div", "palette-grid");
    const colours: Array<{ label: string; get: () => string; set: (value: string) => void }> = [
      { label: "Accent", get: () => card.accent, set: (value) => { card.accent = value; } },
      ...card.palette.map((_, index) => ({
        label: `P${index + 1}`,
        get: () => card.palette[index],
        set: (value: string) => { card.palette[index] = value; },
      })),
    ];
    for (const colour of colours) {
      const colourInput = element("input", "colour-input");
      colourInput.type = "color";
      colourInput.value = /^#[0-9a-f]{6}$/i.test(colour.get()) ? colour.get() : "#000000";
      const hex = textInput(colour.get(), (value) => {
        colour.set(value);
        if (/^#[0-9a-f]{6}$/i.test(value)) colourInput.value = value;
        this.markDirty();
      }, { maxLength: 7 });
      hex.classList.add("colour-hex");
      colourInput.addEventListener("input", () => {
        colour.set(colourInput.value);
        hex.value = colourInput.value;
        this.markDirty();
      });
      palette.append(field(colour.label, element("div", "colour-control", colourInput, hex)));
    }
    const appearance = element(
      "div",
      "editor-section",
      element("h3", "section-title", "02 · Colour system"),
      palette,
    );

    const mediaSelect = element("select", "select-input");
    const media = this.workspace?.media ?? [];
    for (const asset of media.filter((item) => item.status === "ready" || item.id === card.mediaAssetId)) {
      const option = element("option", "", `${asset.originalName} · ${asset.status.toLocaleUpperCase()}`);
      option.value = asset.id;
      option.selected = asset.id === card.mediaAssetId;
      option.disabled = asset.status !== "ready" && asset.id !== card.mediaAssetId;
      mediaSelect.append(option);
    }
    mediaSelect.addEventListener("change", () => {
      const asset = media.find((item) => item.id === mediaSelect.value);
      if (!asset || asset.status !== "ready") return;
      card.mediaAssetId = asset.id;
      card.mediaUrl = asset.mediaUrl;
      card.posterUrl = asset.posterUrl;
      this.markDirty();
      this.renderPageOnly();
    });
    const enabled = element("input", "switch-input");
    enabled.type = "checkbox";
    enabled.checked = card.enabled;
    enabled.addEventListener("change", () => {
      card.enabled = enabled.checked;
      this.markDirty();
      this.renderPageOnly();
    });
    const availability = element(
      "div",
      "editor-section",
      element("h3", "section-title", "03 · Availability"),
      field("Selected media", mediaSelect, "新选择仅显示 Ready；Archived 历史引用仍保留在草稿中。"),
      element(
        "label",
        "switch-row",
        element("span", "switch-copy", element("strong", "", "Enabled"), element("small", "", "停用后不会进入公共卡片序列。")),
        enabled,
        element("span", "switch-visual"),
      ),
    );

    return element(
      "aside",
      "card-editor",
      heading,
      identity,
      appearance,
      availability,
      this.renderCropEditor(card),
    );
  }

  private renderCropEditor(card: ContentCard): HTMLElement {
    const asset = this.workspace?.media.find((item) => item.id === card.mediaAssetId);
    const stage = this.cropStage(card, asset, "desktop");
    const portraitStage = this.cropStage(card, asset, "portrait");
    const focusX = element("input", "range-input");
    focusX.type = "range";
    focusX.min = "0";
    focusX.max = "1";
    focusX.step = "0.01";
    focusX.value = String(card.focusX);
    const focusY = focusX.cloneNode() as HTMLInputElement;
    focusY.value = String(card.focusY);
    const zoom = element("input", "range-input");
    zoom.type = "range";
    zoom.min = String(CONTENT_LIMITS.zoomMin);
    zoom.max = String(CONTENT_LIMITS.zoomMax);
    zoom.step = "0.01";
    zoom.value = String(card.zoom);
    const xValue = element("output", "range-value", card.focusX.toFixed(2));
    const yValue = element("output", "range-value", card.focusY.toFixed(2));
    const zoomValue = element("output", "range-value", `${card.zoom.toFixed(2)}×`);
    const refresh = () => {
      xValue.textContent = card.focusX.toFixed(2);
      yValue.textContent = card.focusY.toFixed(2);
      zoomValue.textContent = `${card.zoom.toFixed(2)}×`;
      this.applyCrop(stage, card, asset);
      this.applyCrop(portraitStage, card, asset);
    };
    focusX.addEventListener("input", () => {
      card.focusX = Number(focusX.value);
      this.markDirty();
      refresh();
    });
    focusY.addEventListener("input", () => {
      card.focusY = Number(focusY.value);
      this.markDirty();
      refresh();
    });
    zoom.addEventListener("input", () => {
      card.zoom = Number(zoom.value);
      this.markDirty();
      refresh();
    });
    queueMicrotask(refresh);

    return element(
      "div",
      "editor-section crop-editor",
      element("h3", "section-title", "04 · Production crop"),
      element(
        "div",
        "crop-previews",
        element("figure", "crop-figure desktop-crop", stage, element("figcaption", "", "DESKTOP · REAL 4:3 CARD")),
        element("figure", "crop-figure portrait-crop", portraitStage, element("figcaption", "", "PORTRAIT CONTEXT")),
      ),
      element("p", "crop-help", "拖动画面定位焦点；焦点框支持方向键微调。使用公共产品同一 MediaFit 计算。"),
      this.rangeRow("Focus X", focusX, xValue),
      this.rangeRow("Focus Y", focusY, yValue),
      this.rangeRow("Zoom", zoom, zoomValue),
    );
  }

  private rangeRow(label: string, input: HTMLInputElement, output: HTMLOutputElement): HTMLElement {
    return element("label", "range-row", element("span", "range-label", label), input, output);
  }

  private cropStage(card: ContentCard, asset: MediaAsset | undefined, context: "desktop" | "portrait"): HTMLElement {
    const stage = element("div", `crop-stage ${context}`);
    stage.tabIndex = 0;
    stage.setAttribute("role", "application");
    stage.setAttribute("aria-label", `${context === "desktop" ? "桌面" : "竖屏"}视频裁切，拖动或使用方向键调整焦点`);
    const video = element("video", "crop-video");
    video.muted = true;
    video.defaultMuted = true;
    video.loop = true;
    video.autoplay = true;
    video.playsInline = true;
    video.preload = "metadata";
    if (asset?.mediaUrl) video.src = asset.mediaUrl;
    if (asset?.posterUrl) video.poster = asset.posterUrl;
    const marker = element("span", "focus-marker", element("span", "focus-dot"));
    const veil = element("span", "crop-veil", context === "portrait" ? "MOBILE" : "COVER");
    stage.append(video, veil, marker);
    video.addEventListener("canplay", () => void video.play().catch(() => undefined), { once: true });
    video.addEventListener("error", () => stage.classList.add("has-media-error"));

    let startX = 0;
    let startY = 0;
    let startFocusX = card.focusX;
    let startFocusY = card.focusY;
    stage.addEventListener("pointerdown", (event) => {
      stage.setPointerCapture(event.pointerId);
      startX = event.clientX;
      startY = event.clientY;
      startFocusX = card.focusX;
      startFocusY = card.focusY;
      stage.classList.add("is-dragging");
    });
    stage.addEventListener("pointermove", (event) => {
      if (!stage.hasPointerCapture(event.pointerId) || !asset) return;
      const selectedAsset = asset;
      const fit = computeMediaFit(selectedAsset.width || 1920, selectedAsset.height || 1080, TARGET_GRID.planeAspect, 1, "cover", card);
      const rect = stage.getBoundingClientRect();
      const xDenominator = Math.max(0.001, 1 - fit.repeatX);
      const yDenominator = Math.max(0.001, 1 - fit.repeatY);
      card.focusX = clamp(startFocusX - ((event.clientX - startX) / rect.width) * fit.repeatX / xDenominator, 0, 1);
      card.focusY = clamp(startFocusY - ((event.clientY - startY) / rect.height) * fit.repeatY / yDenominator, 0, 1);
      this.markDirty();
      this.applyAllVisibleCrops(card, selectedAsset);
      this.updateCropReadouts(card);
    });
    const release = (event: PointerEvent) => {
      if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
      stage.classList.remove("is-dragging");
    };
    stage.addEventListener("pointerup", release);
    stage.addEventListener("pointercancel", release);
    stage.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 0.01 : 0.025;
      if (event.key === "ArrowLeft") card.focusX = clamp(card.focusX - step, 0, 1);
      else if (event.key === "ArrowRight") card.focusX = clamp(card.focusX + step, 0, 1);
      else if (event.key === "ArrowUp") card.focusY = clamp(card.focusY - step, 0, 1);
      else if (event.key === "ArrowDown") card.focusY = clamp(card.focusY + step, 0, 1);
      else return;
      event.preventDefault();
      this.markDirty();
      if (asset) this.applyAllVisibleCrops(card, asset);
      this.updateCropReadouts(card);
    });
    return stage;
  }

  private applyAllVisibleCrops(card: ContentCard, asset: MediaAsset): void {
    this.root.querySelectorAll<HTMLElement>(".crop-stage").forEach((stage) => this.applyCrop(stage, card, asset));
  }

  private applyCrop(stage: HTMLElement, card: ContentCard, asset?: MediaAsset): void {
    if (!asset) return;
    const fit = computeMediaFit(
      asset.width || 1920,
      asset.height || 1080,
      TARGET_GRID.planeAspect,
      1,
      "cover",
      { focusX: card.focusX, focusY: card.focusY, zoom: card.zoom },
    );
    const video = stage.querySelector<HTMLElement>(".crop-video");
    const marker = stage.querySelector<HTMLElement>(".focus-marker");
    if (video) {
      const topVisible = 1 - fit.offsetY - fit.repeatY;
      video.style.width = `${100 / fit.repeatX}%`;
      video.style.height = `${100 / fit.repeatY}%`;
      video.style.left = `${(-fit.offsetX / fit.repeatX) * 100}%`;
      video.style.top = `${(-topVisible / fit.repeatY) * 100}%`;
    }
    if (marker) {
      marker.style.left = `${card.focusX * 100}%`;
      marker.style.top = `${card.focusY * 100}%`;
    }
  }

  private updateCropReadouts(card: ContentCard): void {
    const outputs = this.root.querySelectorAll<HTMLOutputElement>(".range-value");
    if (outputs[0]) outputs[0].textContent = card.focusX.toFixed(2);
    if (outputs[1]) outputs[1].textContent = card.focusY.toFixed(2);
    if (outputs[2]) outputs[2].textContent = `${card.zoom.toFixed(2)}×`;
    const inputs = this.root.querySelectorAll<HTMLInputElement>(".range-input");
    if (inputs[0]) inputs[0].value = String(card.focusX);
    if (inputs[1]) inputs[1].value = String(card.focusY);
  }

  private currentCard(): ContentCard | undefined {
    return this.manifest?.cards.find((card) => card.id === this.selectedCardId);
  }

  private editCard<K extends "code" | "category" | "title" | "deck">(
    card: ContentCard,
    key: K,
    value: ContentCard[K],
  ): void {
    card[key] = value;
    this.markDirty();
  }

  private createCard(): void {
    if (!this.manifest || !this.workspace) return;
    const asset = this.workspace.media.find((item) => item.status === "ready");
    if (!asset) {
      this.showToast("请先上传至少一个 Ready 视频。", "打开媒体库", () => this.navigate("media"));
      return;
    }
    let suffix = this.manifest.cards.length + 1;
    let code = `ILG—${suffix}`;
    const codes = new Set(this.manifest.cards.map((card) => card.code.toLocaleLowerCase()));
    while (codes.has(code.toLocaleLowerCase())) code = `ILG—${++suffix}`;
    const card: ContentCard = {
      id: crypto.randomUUID(),
      code,
      category: "EDITORIAL",
      title: "Untitled Story",
      deck: "Describe the story this card should introduce.",
      accent: "#d7ff3f",
      palette: ["#10120e", "#40512a", "#a4bd5a", "#f2f5e9"],
      mediaAssetId: asset.id,
      mediaUrl: asset.mediaUrl,
      posterUrl: asset.posterUrl,
      focusX: 0.5,
      focusY: 0.5,
      zoom: 1,
      enabled: false,
      sortOrder: this.manifest.cards.length,
    };
    this.manifest.cards.push(card);
    this.selectedCardId = card.id;
    this.markDirty();
    this.renderPageOnly();
    queueMicrotask(() => this.root.querySelector<HTMLInputElement>(".card-editor .text-input")?.focus());
  }

  private duplicateCard(source: ContentCard): void {
    if (!this.manifest) return;
    const copy = structuredClone(source);
    copy.id = crypto.randomUUID();
    const baseCode = `${source.code} COPY`;
    let code = baseCode;
    let index = 2;
    const codes = new Set(this.manifest.cards.map((card) => card.code.toLocaleLowerCase()));
    while (codes.has(code.toLocaleLowerCase())) code = `${baseCode} ${index++}`;
    copy.code = code.slice(0, CONTENT_LIMITS.code);
    copy.title = `${source.title} Copy`.slice(0, CONTENT_LIMITS.title);
    copy.enabled = false;
    copy.sortOrder = this.manifest.cards.length;
    this.manifest.cards.push(copy);
    this.selectedCardId = copy.id;
    this.markDirty();
    this.renderPageOnly();
    this.showToast("已复制为停用卡片。发布前请检查 Code 和内容。", "查看", () => undefined);
  }

  private removeCard(card: ContentCard): void {
    if (!this.manifest) return;
    const index = this.manifest.cards.findIndex((item) => item.id === card.id);
    if (index < 0) return;
    this.removedCard = { card: structuredClone(card), index };
    this.manifest.cards.splice(index, 1);
    this.manifest.cards = sortCards(this.manifest.cards);
    this.selectedCardId = this.manifest.cards[Math.min(index, this.manifest.cards.length - 1)]?.id;
    this.markDirty();
    this.renderPageOnly();
    this.showToast(`“${card.title}”已从草稿移除，媒体未删除。`, "撤销", () => this.undoRemove());
  }

  private undoRemove(): void {
    if (!this.manifest || !this.removedCard) return;
    const { card, index } = this.removedCard;
    this.manifest.cards.splice(index, 0, card);
    this.manifest.cards = sortCards(this.manifest.cards);
    this.selectedCardId = card.id;
    this.removedCard = undefined;
    this.markDirty();
    this.renderPageOnly();
  }

  private reorderCard(sourceId: string, targetId: string): void {
    if (!this.manifest || sourceId === targetId) return;
    const cards = sortCards(this.manifest.cards);
    const sourceIndex = cards.findIndex((card) => card.id === sourceId);
    const targetIndex = cards.findIndex((card) => card.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const [source] = cards.splice(sourceIndex, 1);
    cards.splice(targetIndex, 0, source);
    this.manifest.cards = sortCards(cards);
    this.markDirty();
    this.renderPageOnly();
  }

  private moveCard(cardId: string, delta: number): void {
    if (!this.manifest) return;
    const cards = sortCards(this.manifest.cards);
    const index = cards.findIndex((card) => card.id === cardId);
    const target = clamp(index + delta, 0, cards.length - 1);
    if (index < 0 || target === index) return;
    const targetId = cards[target].id;
    this.reorderCard(cardId, targetId);
    queueMicrotask(() => this.root.querySelector<HTMLButtonElement>(`[data-card-id="${CSS.escape(cardId)}"] .drag-handle`)?.focus());
  }

  private renderMediaPage(): HTMLElement {
    const page = element("section", "page page-media");
    page.append(this.pageHeading("02 / ASSET ROOM", "Media Library", "MP4 入库、Poster、版本化替换与引用保护。"));
    const input = element("input", "visually-hidden");
    input.type = "file";
    input.accept = ".mp4,video/mp4";
    input.id = "media-upload";
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file) void this.uploadFile(file);
      input.value = "";
    });
    const upload = element(
      "label",
      "upload-strip",
      element("span", "upload-mark", "↑"),
      element(
        "span",
        "upload-copy",
        element("strong", "", "Upload public-ready MP4"),
        element("small", "", "MIME + extension validation · 100 MB max · browser poster + SHA-256"),
      ),
      element("span", "button button-accent", "选择文件"),
      input,
    );
    page.append(upload, this.renderUploadJob());
    page.append(
      element(
        "div",
        "media-notice",
        element("strong", "", "Compatibility note"),
        element("span", "", "建议使用 H.264 MP4，以兼容 Safari 与移动端。未发布上传若 URL 已知，技术上仍可公开访问。"),
      ),
    );

    const assets = this.workspace?.media ?? [];
    const library = element("div", "media-library");
    for (const asset of assets) library.append(this.renderMediaAsset(asset));
    if (!assets.length) library.append(element("div", "empty-state", "媒体库为空。上传第一支 MP4 开始。"));
    page.append(element("div", "section-rule", element("span", "", `${assets.length} ASSETS`)), library);
    return page;
  }

  private renderUploadJob(): HTMLElement {
    const job = this.uploadJob;
    if (!job) return element("div", "upload-job is-empty");
    const progress = element("progress", "upload-progress");
    progress.max = 100;
    progress.value = job.progress.value;
    const cancel = textButton("取消", "button button-danger compact", () => job.controller.abort());
    const actions = element("div", "upload-job-actions", cancel);
    if (job.error && this.retryFile) {
      actions.append(textButton("重试", "button button-quiet compact", () => void this.uploadFile(this.retryFile as File)));
    }
    return element(
      "div",
      `upload-job${job.error ? " has-error" : ""}`,
      element("div", "upload-job-copy", element("strong", "", job.file.name), element("span", "", job.error ?? job.message)),
      progress,
      element("output", "upload-percent", `${Math.round(job.progress.value)}%`),
      actions,
    );
  }

  private renderMediaAsset(asset: MediaAsset): HTMLElement {
    const references = this.mediaReferences(asset.id);
    const totalReferences = references.draft + references.published + references.history;
    const visual = element("div", "media-visual");
    if (asset.posterUrl) {
      const poster = element("img", "media-poster");
      poster.src = asset.posterUrl;
      poster.alt = "";
      poster.loading = "lazy";
      visual.append(poster);
    } else {
      const video = element("video", "media-poster");
      video.src = asset.mediaUrl;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      visual.append(video);
    }
    visual.append(element("span", `status-pill media-status is-${asset.status}`, asset.status.toLocaleUpperCase()));

    const details = element(
      "div",
      "media-details",
      element("strong", "media-name", asset.originalName),
      element(
        "span",
        "media-meta",
        `${asset.width || "—"}×${asset.height || "—"} · ${formatDuration(asset.durationMs)} · ${formatBytes(asset.sizeBytes)}`,
      ),
      element("span", "media-path", asset.storagePath),
      element(
        "div",
        "reference-meter",
        element("span", "", `DRAFT ${references.draft}`),
        element("span", "", `ACTIVE ${references.published}`),
        element("span", "", `HISTORY ${references.history}`),
      ),
    );

    const actions = element("div", "media-actions");
    if (asset.status === "ready") {
      const replaceInput = element("input", "visually-hidden");
      replaceInput.type = "file";
      replaceInput.accept = ".mp4,video/mp4";
      const replace = element("label", "button button-quiet compact", "替换", replaceInput);
      replaceInput.addEventListener("change", () => {
        const file = replaceInput.files?.[0];
        if (file) void this.replaceMedia(asset, file);
      });
      actions.append(replace);
    }
    const archive = textButton("归档", "button button-quiet compact", () => void this.archiveMedia(asset));
    archive.disabled = asset.status === "archived";
    const purge = textButton("永久删除", "button button-danger compact", () => void this.purgeMedia(asset));
    purge.disabled = totalReferences > 0 || asset.status !== "archived";
    purge.title = totalReferences > 0
      ? "草稿、线上或历史版本仍有引用"
      : asset.status !== "archived" ? "请先归档" : "零引用，可永久删除";
    actions.append(archive, purge);

    return element("article", "media-asset", visual, details, actions);
  }

  private mediaReferences(mediaId: string): { draft: number; published: number; history: number } {
    const count = (manifest: ContentManifest | undefined) => manifest?.cards.filter((card) => card.mediaAssetId === mediaId).length ?? 0;
    return {
      draft: count(this.manifest),
      published: count(this.workspace?.published),
      history: this.workspace?.history.reduce((total, version) => total + count(version.manifest), 0) ?? 0,
    };
  }

  private async uploadFile(file: File): Promise<MediaAsset | undefined> {
    if (this.uploadJob) this.uploadJob.controller.abort();
    const controller = new AbortController();
    this.retryFile = file;
    this.uploadJob = {
      file,
      controller,
      progress: { phase: "preparing", value: 2 },
      message: "正在读取元数据、生成 Poster 与 SHA-256…",
    };
    this.renderPageOnly();
    try {
      const prepared = await prepareMedia(file);
      if (controller.signal.aborted) throw new AdapterError("cancelled", "上传已取消");
      const duplicate = this.workspace?.media.find((asset) => asset.sha256 && asset.sha256 === prepared.sha256);
      if (duplicate && !window.confirm(`SHA-256 与“${duplicate.originalName}”一致，仍继续上传？`)) {
        throw new AdapterError("cancelled", "检测到重复文件，已取消上传");
      }
      const asset = await this.adapter.uploadMedia(prepared, controller.signal, (progress) => {
        if (!this.uploadJob) return;
        this.uploadJob.progress = progress;
        this.uploadJob.message = this.uploadPhaseLabel(progress.phase);
        this.updateUploadReadout();
      });
      this.workspace?.media.unshift(asset);
      this.uploadJob = undefined;
      this.retryFile = undefined;
      this.renderPageOnly();
      this.showToast(`“${asset.originalName}”已 Ready。`);
      return asset;
    } catch (error) {
      if (!this.uploadJob) return undefined;
      this.uploadJob.error = this.errorMessage(error);
      this.uploadJob.message = "上传未完成";
      this.renderPageOnly();
      return undefined;
    }
  }

  private updateUploadReadout(): void {
    const job = this.uploadJob;
    if (!job) return;
    const progress = this.root.querySelector<HTMLProgressElement>(".upload-progress");
    const percent = this.root.querySelector<HTMLOutputElement>(".upload-percent");
    const message = this.root.querySelector<HTMLElement>(".upload-job-copy span");
    if (progress) progress.value = job.progress.value;
    if (percent) percent.textContent = `${Math.round(job.progress.value)}%`;
    if (message) message.textContent = job.message;
  }

  private uploadPhaseLabel(phase: UploadProgress["phase"]): string {
    switch (phase) {
      case "video": return "正在上传视频…";
      case "poster": return "正在上传 Poster…";
      case "registering": return "正在登记媒体记录…";
      case "done": return "媒体已 Ready";
      default: return "正在准备媒体…";
    }
  }

  private async replaceMedia(oldAsset: MediaAsset, file: File): Promise<void> {
    const replacement = await this.uploadFile(file);
    if (!replacement || !this.manifest) return;
    let changed = 0;
    for (const card of this.manifest.cards) {
      if (card.mediaAssetId !== oldAsset.id) continue;
      card.mediaAssetId = replacement.id;
      card.mediaUrl = replacement.mediaUrl;
      card.posterUrl = replacement.posterUrl;
      changed += 1;
    }
    if (changed) this.markDirty();
    try {
      const archived = await this.adapter.archiveMedia(oldAsset.id);
      this.replaceWorkspaceAsset(archived);
    } catch (error) {
      this.showToast(`新媒体已上传，但旧媒体归档失败：${this.errorMessage(error)}`);
    }
    this.renderPageOnly();
    this.showToast(`不可变替换完成；${changed} 张草稿卡片已改用新资产。`);
  }

  private async archiveMedia(asset: MediaAsset): Promise<void> {
    if (!window.confirm(`归档“${asset.originalName}”？已发布与历史引用仍会保留。`)) return;
    try {
      const archived = await this.adapter.archiveMedia(asset.id);
      this.replaceWorkspaceAsset(archived);
      this.renderPageOnly();
      this.showToast("媒体已归档。新卡片不能再选择它。");
    } catch (error) {
      this.showToast(this.errorMessage(error));
    }
  }

  private async purgeMedia(asset: MediaAsset): Promise<void> {
    const refs = this.mediaReferences(asset.id);
    const total = refs.draft + refs.published + refs.history;
    if (total > 0) return this.showToast(`永久删除被阻止：仍有 ${total} 个引用。`);
    if (asset.status !== "archived") return this.showToast("请先归档，再执行永久删除。");
    if (!window.confirm(`永久删除“${asset.originalName}”及其 Poster？此操作无法撤销。`)) return;
    try {
      await this.adapter.purgeMedia(asset);
      if (this.workspace) this.workspace.media = this.workspace.media.filter((item) => item.id !== asset.id);
      this.renderPageOnly();
      this.showToast("零引用媒体及数据库记录已永久删除。" );
    } catch (error) {
      this.showToast(this.errorMessage(error));
    }
  }

  private replaceWorkspaceAsset(asset: MediaAsset): void {
    if (!this.workspace) return;
    const index = this.workspace.media.findIndex((item) => item.id === asset.id);
    if (index >= 0) this.workspace.media[index] = asset;
  }

  private renderSettingsPage(): HTMLElement {
    const page = element("section", "page page-settings");
    page.append(this.pageHeading("03 / SITE VOICE", "Site Settings", "只编辑品牌与 CTA 内容，不触碰 Footer presentation CSS。"));
    const site = this.manifest?.site;
    if (!site) return page;
    const form = element("div", "settings-form");
    const bind = <K extends keyof typeof site>(key: K, value: string) => {
      site[key] = value;
      this.markDirty();
    };
    form.append(
      element(
        "div",
        "settings-block",
        element("span", "settings-number", "01"),
        element(
          "div",
          "settings-fields",
          element("h2", "settings-title", "Footer identity"),
          field("Footer caption", textInput(site.footerCaption, (value) => bind("footerCaption", value), { maxLength: CONTENT_LIMITS.footerCaption })),
          field("Brand text", textInput(site.brandText, (value) => bind("brandText", value), { maxLength: CONTENT_LIMITS.compactSiteText })),
          field("Brand URL", textInput(site.brandUrl, (value) => bind("brandUrl", value), { maxLength: CONTENT_LIMITS.url, type: "url" }), "仅允许 https"),
        ),
      ),
      element(
        "div",
        "settings-block",
        element("span", "settings-number", "02"),
        element(
          "div",
          "settings-fields",
          element("h2", "settings-title", "Call to action"),
          field("CTA label", textInput(site.ctaLabel, (value) => bind("ctaLabel", value), { maxLength: CONTENT_LIMITS.compactSiteText })),
          field("CTA URL", textInput(site.ctaUrl, (value) => bind("ctaUrl", value), { maxLength: CONTENT_LIMITS.url }), "允许 https 或 mailto"),
        ),
      ),
      element(
        "div",
        "settings-block",
        element("span", "settings-number", "03"),
        element(
          "div",
          "settings-fields",
          element("h2", "settings-title", "Loader"),
          field("Loader brand text", textInput(site.loaderBrandText, (value) => bind("loaderBrandText", value), { maxLength: CONTENT_LIMITS.compactSiteText })),
          element("p", "settings-note", "Loader 动画、Typography 与 Entry choreography 保持冻结；这里只替换文字。"),
        ),
      ),
    );
    const validation = validateManifest(this.manifest as ContentManifest, this.workspace?.media ?? [], "draft")
      .filter((issue) => issue.path.startsWith("site."));
    if (validation.length) {
      form.append(this.issueList(validation.map((issue) => `${issue.path}: ${issue.message}`), "SETTINGS NEED ATTENTION"));
    }
    page.append(form);
    return page;
  }

  private renderHistoryPage(): HTMLElement {
    const page = element("section", "page page-history");
    page.append(this.pageHeading("04 / RELEASE LOG", "Publish History", "不可变快照；恢复只会复制到草稿，仍需再次发布。"));
    const history = this.workspace?.history ?? [];
    const table = element("div", "history-table");
    table.append(
      element(
        "div",
        "history-row history-head",
        element("span", "", "VERSION"),
        element("span", "", "DATE / ADMIN"),
        element("span", "", "RELEASE NOTE"),
        element("span", "", "CARDS"),
        element("span", "", "ACTIONS"),
      ),
    );
    for (const version of history) {
      const view = textButton("View", "button button-quiet compact", () => this.showVersion(version));
      const restore = textButton("Restore to Draft", "button button-quiet compact", () => void this.restoreVersion(version));
      table.append(
        element(
          "div",
          "history-row",
          element("strong", "history-version", `v${version.version}`),
          element("span", "history-date", `${dateLabel(version.createdAt)}\n${version.createdBy}`),
          element("span", "history-note", version.releaseNote || "No release note"),
          element("span", "history-count", String(version.manifest.cards.length)),
          element("div", "history-actions", view, restore),
        ),
      );
    }
    if (!history.length) table.append(element("div", "empty-state", "尚无发布版本。"));
    page.append(table);
    return page;
  }

  private showVersion(version: ContentVersion): void {
    const dialog = this.dialog("Version inspection", `v${version.version}`);
    const body = element("div", "version-inspection");
    body.append(
      element("p", "version-meta", `${dateLabel(version.createdAt)} · ${version.createdBy}`),
      element("p", "version-note", version.releaseNote || "No release note"),
      element("div", "version-card-list"),
    );
    const list = body.querySelector<HTMLElement>(".version-card-list");
    version.manifest.cards.forEach((card, index) => {
      list?.append(
        element(
          "div",
          "version-card",
          element("span", "", String(index + 1).padStart(2, "0")),
          element("strong", "", card.title),
          element("span", "", card.code),
          element("span", `status-pill ${card.enabled ? "is-ready" : "is-muted"}`, card.enabled ? "ENABLED" : "DISABLED"),
        ),
      );
    });
    dialog.querySelector(".dialog-body")?.append(body);
    document.body.append(dialog);
    dialog.showModal();
  }

  private async restoreVersion(version: ContentVersion): Promise<void> {
    if (!window.confirm(`把 v${version.version} 复制到当前草稿？这不会直接改变线上版本。`)) return;
    try {
      const draft = await this.adapter.restoreToDraft(version.id);
      if (!this.workspace) return;
      this.workspace.draft = draft;
      this.manifest = cloneManifest(draft.manifest);
      this.savedManifest = cloneManifest(draft.manifest);
      this.selectedCardId = this.manifest.cards[0]?.id;
      this.saveState = "clean";
      this.saveMessage = `已恢复 v${version.version} 到草稿`;
      this.persistPreviewDraft();
      this.renderShell();
      this.showToast("历史版本已恢复到草稿。检查后请执行一次新的 Publish。" );
    } catch (error) {
      this.showToast(this.errorMessage(error));
    }
  }

  private renderPreviewPage(): HTMLElement {
    const page = element("section", "page page-preview");
    page.append(this.pageHeading("05 / PRODUCTION RENDERER", "Draft Preview", "真实生产渲染器，不发布草稿，不热替换运行中的 VideoTexture。"));
    const mode = element("div", "segmented");
    for (const [value, label] of [["draft", "Draft"], ["published", "Published"]] as const) {
      const button = textButton(label, `segment${this.previewMode === value ? " is-active" : ""}`, () => {
        this.previewMode = value;
        this.renderPageOnly();
      });
      button.setAttribute("aria-pressed", String(this.previewMode === value));
      mode.append(button);
    }
    const preset = element("select", "select-input preview-preset");
    const presets: Array<[PreviewPreset, string]> = [
      ["desktop", "Desktop · 1440×900"],
      ["portrait", "Mobile portrait · 390×844"],
      ["landscape", "Mobile landscape · 844×390"],
    ];
    for (const [value, label] of presets) {
      const option = element("option", "", label);
      option.value = value;
      option.selected = value === this.previewPreset;
      preset.append(option);
    }
    preset.addEventListener("change", () => {
      this.previewPreset = preset.value as PreviewPreset;
      this.renderPageOnly();
    });
    const reload = textButton("↻ Reload preview", "button button-quiet", () => this.reloadPreview());
    const publicLink = element("a", "button button-quiet", "Open public ↗");
    publicLink.href = "/";
    publicLink.target = "_blank";
    publicLink.rel = "noreferrer";
    page.append(element("div", "preview-toolbar", mode, preset, reload, publicLink));

    this.persistPreviewDraft();
    const dimensions = this.previewDimensions();
    const frame = element("iframe", "preview-frame");
    frame.title = `${this.previewMode === "draft" ? "草稿" : "当前发布"} ${dimensions.width}×${dimensions.height} 预览`;
    frame.width = String(dimensions.width);
    frame.height = String(dimensions.height);
    frame.src = this.previewUrl();
    frame.dataset.previewMode = this.previewMode;
    const device = element("div", `preview-device is-${this.previewPreset}`, frame);
    device.dataset.width = String(dimensions.width);
    device.dataset.height = String(dimensions.height);
    const stage = element("div", "preview-stage", device);
    page.append(
      element(
        "div",
        "preview-status",
        element("span", `status-pill ${this.previewMode === "draft" ? "is-warning" : "is-ready"}`, this.previewMode.toLocaleUpperCase()),
        element("span", "", `${dimensions.width}×${dimensions.height}`),
        element("span", "", this.previewMode === "draft" ? "ADMIN ONLY" : `ACTIVE v${this.workspace?.published.version ?? "—"}`),
      ),
      stage,
    );
    queueMicrotask(() => this.fitPreview(stage, device, dimensions.width, dimensions.height));
    return page;
  }

  private previewDimensions(): { width: number; height: number } {
    if (this.previewPreset === "portrait") return { width: 390, height: 844 };
    if (this.previewPreset === "landscape") return { width: 844, height: 390 };
    return { width: 1440, height: 900 };
  }

  private previewUrl(): string {
    const dimensions = this.previewDimensions();
    const url = new URL("/draft-preview.html", location.origin);
    url.searchParams.set("content", this.previewMode);
    url.searchParams.set("viewport", `${dimensions.width}x${dimensions.height}`);
    return `${url.pathname}${url.search}`;
  }

  private fitPreview(stage: HTMLElement, device: HTMLElement, width: number, height: number): void {
    const apply = () => {
      const availableWidth = Math.max(280, stage.clientWidth - 32);
      const availableHeight = Math.max(300, Math.min(760, window.innerHeight - 230));
      const scale = Math.min(1, availableWidth / width, availableHeight / height);
      const scaledWidth = width * scale;
      device.style.width = `${width}px`;
      device.style.height = `${height}px`;
      device.style.left = `${Math.max(16, (stage.clientWidth - scaledWidth) / 2)}px`;
      device.style.transform = `scale(${scale})`;
      stage.style.height = `${height * scale + 32}px`;
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(stage);
    window.setTimeout(() => observer.disconnect(), 20_000);
  }

  private reloadPreview(): void {
    this.persistPreviewDraft();
    const frame = this.root.querySelector<HTMLIFrameElement>(".preview-frame");
    if (frame) frame.src = this.previewUrl();
  }

  private persistPreviewDraft(): void {
    if (!this.manifest) return;
    sessionStorage.setItem("mirrorweb.admin.preview-draft", JSON.stringify(this.manifest));
  }

  private markDirty(): void {
    this.editSerial += 1;
    this.saveState = "dirty";
    this.saveMessage = "有未保存修改";
    this.conflictMessage = undefined;
    this.persistPreviewDraft();
    this.updateSaveReadout();
    this.updateRailStats();
    if (this.saveTimer) window.clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(() => void this.saveNow(false), 900);
  }

  private async saveNow(manual: boolean): Promise<void> {
    if (!this.manifest || !this.workspace) return;
    if (this.saveTimer) window.clearTimeout(this.saveTimer);
    if (this.saveState === "saving") return;
    if (this.saveState === "clean") {
      if (manual) this.showToast("草稿已经是最新状态。" );
      return;
    }
    const issues = validateManifest(this.manifest, this.workspace.media, "draft");
    if (issues.length) {
      this.saveState = "invalid";
      this.saveMessage = `草稿有 ${issues.length} 项需修正`;
      this.updateSaveReadout();
      if (manual) this.showIssuesDialog("Draft validation", issues.map((issue) => `${issue.path}: ${issue.message}`));
      return;
    }
    const serial = this.editSerial;
    const payload = cloneManifest(this.manifest);
    this.saveState = "saving";
    this.saveMessage = "正在保存…";
    this.updateSaveReadout();
    try {
      const draft = await this.adapter.saveDraft(payload, this.workspace.draft.revision);
      this.workspace.draft = draft;
      this.savedManifest = cloneManifest(payload);
      if (serial === this.editSerial) {
        this.saveState = "clean";
        this.saveMessage = `已保存 ${dateLabel(draft.updatedAt)}`;
      } else {
        this.saveState = "dirty";
        this.saveMessage = "保存期间有新修改";
        this.saveTimer = window.setTimeout(() => void this.saveNow(false), 700);
      }
    } catch (error) {
      if (error instanceof AdapterError && error.code === "conflict") {
        this.saveState = "conflict";
        this.saveMessage = "Revision 冲突";
        this.conflictMessage = error.message;
        this.renderPageOnly();
      } else {
        this.saveState = "error";
        this.saveMessage = "保存失败";
        if (manual) this.showToast(this.errorMessage(error));
      }
    } finally {
      this.updateSaveReadout();
    }
  }

  private updateSaveReadout(): void {
    const readout = this.root.querySelector<HTMLElement>("#save-readout");
    if (readout) {
      readout.dataset.state = this.saveState;
      const label = readout.querySelector<HTMLElement>(".save-label");
      const revision = readout.querySelector<HTMLElement>(".revision-label");
      if (label) label.textContent = this.saveMessage;
      if (revision) revision.textContent = `r${this.workspace?.draft.revision ?? 0}`;
    }
    const save = this.root.querySelector<HTMLButtonElement>("#manual-save");
    if (save) save.disabled = this.saveState === "saving" || this.saveState === "clean";
  }

  private updateRailStats(): void {
    const total = this.root.querySelector<HTMLElement>(".rail-stat-value");
    const enabled = this.root.querySelector<HTMLElement>(".rail-stat-note");
    if (total) total.textContent = `${this.manifest?.cards.length ?? 0} cards`;
    if (enabled) enabled.textContent = `${this.manifest?.cards.filter((card) => card.enabled).length ?? 0} enabled`;
  }

  private renderConflict(): HTMLElement {
    return element(
      "div",
      "conflict-banner",
      element("span", "conflict-mark", "!"),
      element(
        "div",
        "conflict-copy",
        element("strong", "", "草稿 revision 已变化"),
        element("span", "", this.conflictMessage ?? "另一窗口或管理员已保存了新版本。"),
      ),
      textButton("重新读取远程草稿", "button button-quiet", () => void this.reloadAfterConflict()),
    );
  }

  private async reloadAfterConflict(): Promise<void> {
    if (!window.confirm("重新读取会丢弃当前未保存修改。继续？")) return;
    await this.loadWorkspace();
  }

  private openPublishDialog(): void {
    if (!this.manifest || !this.workspace) return;
    const issues = validateManifest(this.manifest, this.workspace.media, "publish");
    const dialog = this.dialog("Publish content", `DRAFT r${this.workspace.draft.revision}`);
    const body = dialog.querySelector<HTMLElement>(".dialog-body");
    if (!body) return;
    const diff = this.diffManifest(this.workspace.published, this.manifest);
    body.append(
      element(
        "div",
        "publish-summary",
        this.summaryMetric("Changed", diff.changed.length),
        this.summaryMetric("Added", diff.added.length),
        this.summaryMetric("Removed / off", diff.removedOrDisabled.length),
        this.summaryMetric("Media changes", diff.media.length),
      ),
      this.changeSection("CHANGED CARDS", diff.changed),
      this.changeSection("ADDED CARDS", diff.added),
      this.changeSection("REMOVED / DISABLED", diff.removedOrDisabled),
      this.changeSection("MEDIA REPLACED", diff.media),
    );
    const releaseNote = textArea("", () => undefined, 500);
    releaseNote.placeholder = "What changed, and why?";
    body.append(field("Release note", releaseNote));
    if (this.saveState !== "clean") {
      body.append(element("p", "publish-warning", "当前有未保存修改；确认发布时会先保存草稿。"));
    }
    if (issues.length) body.append(this.issueList(issues.map((issue) => `${issue.path}: ${issue.message}`), "PUBLISH BLOCKED"));
    else body.append(element("div", "validation-pass", "✓ Final validation passed"));

    const confirm = textButton("Publish new version", "button button-accent", async () => {
      confirm.disabled = true;
      try {
        if (this.saveState !== "clean") await this.saveNow(true);
        if (this.saveState !== "clean" || !this.workspace || !this.manifest) {
          throw new AdapterError("validation", "草稿尚未成功保存，发布已停止");
        }
        const finalIssues = validateManifest(this.manifest, this.workspace.media, "publish");
        if (finalIssues.length) throw new AdapterError("validation", "最终校验未通过");
        const version = await this.adapter.publish(this.workspace.draft.revision, releaseNote.value);
        this.workspace.published = cloneManifest(version.manifest);
        this.workspace.history.unshift(version);
        this.workspace.draft = {
          ...this.workspace.draft,
          manifest: cloneManifest(version.manifest),
          revision: version.draftRevision ?? this.workspace.draft.revision + 1,
          updatedBy: this.actor?.email ?? this.workspace.draft.updatedBy,
          updatedAt: version.createdAt,
        };
        this.manifest = cloneManifest(version.manifest);
        this.savedManifest = cloneManifest(version.manifest);
        this.saveState = "clean";
        this.saveMessage = `v${version.version} 已发布`;
        this.persistPreviewDraft();
        this.updateSaveReadout();
        dialog.close();
        this.showToast(`v${version.version} 已发布。新访客和刷新后的页面将读取新版本。`, "打开公共页", () => window.open("/", "_blank", "noopener"));
        if (this.page === "history") this.renderPageOnly();
      } catch (error) {
        this.showToast(this.errorMessage(error));
        confirm.disabled = false;
      }
    });
    confirm.disabled = issues.length > 0;
    const footer = dialog.querySelector<HTMLElement>(".dialog-footer");
    footer?.append(confirm);
    document.body.append(dialog);
    dialog.showModal();
  }

  private diffManifest(before: ContentManifest, after: ContentManifest): {
    changed: string[];
    added: string[];
    removedOrDisabled: string[];
    media: string[];
  } {
    const previous = new Map(before.cards.map((card) => [card.id, card]));
    const next = new Map(after.cards.map((card) => [card.id, card]));
    const added: string[] = [];
    const changed: string[] = [];
    const removedOrDisabled: string[] = [];
    const media: string[] = [];
    for (const card of after.cards) {
      const old = previous.get(card.id);
      if (!old) added.push(`${card.code} · ${card.title}`);
      else {
        if (!cardsEqual(old, card)) changed.push(`${card.code} · ${card.title}`);
        if (old.mediaAssetId !== card.mediaAssetId) media.push(`${card.code} · ${old.mediaAssetId} → ${card.mediaAssetId}`);
        if (old.enabled && !card.enabled) removedOrDisabled.push(`${card.code} · ${card.title} (disabled)`);
      }
    }
    for (const card of before.cards) {
      if (!next.has(card.id)) removedOrDisabled.push(`${card.code} · ${card.title} (removed)`);
    }
    if (JSON.stringify(before.site) !== JSON.stringify(after.site)) changed.push("Site Settings");
    return { changed, added, removedOrDisabled, media };
  }

  private summaryMetric(label: string, value: number): HTMLElement {
    return element("div", "summary-metric", element("strong", "", String(value).padStart(2, "0")), element("span", "", label));
  }

  private changeSection(title: string, values: string[]): HTMLElement {
    const section = element("section", "change-section", element("h3", "", title));
    if (!values.length) section.append(element("p", "muted", "None"));
    else values.forEach((value) => section.append(element("p", "change-line", value)));
    return section;
  }

  private issueList(issues: string[], title: string): HTMLElement {
    const list = element("div", "issue-list", element("strong", "", title));
    issues.forEach((issue) => list.append(element("p", "", issue)));
    return list;
  }

  private showIssuesDialog(title: string, issues: string[]): void {
    const dialog = this.dialog(title, `${issues.length} ISSUES`);
    dialog.querySelector(".dialog-body")?.append(this.issueList(issues, "NEEDS ATTENTION"));
    document.body.append(dialog);
    dialog.showModal();
  }

  private dialog(title: string, eyebrow: string): HTMLDialogElement {
    const dialog = element("dialog", "admin-dialog");
    const close = iconButton("关闭", "×", () => dialog.close());
    const header = element(
      "header",
      "dialog-header",
      element("div", "", element("span", "eyebrow", eyebrow), element("h2", "dialog-title", title)),
      close,
    );
    const body = element("div", "dialog-body");
    const footer = element("footer", "dialog-footer", textButton("Cancel", "button button-quiet", () => dialog.close()));
    dialog.append(header, body, footer);
    dialog.addEventListener("close", () => dialog.remove());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    return dialog;
  }

  private showToast(message: string, actionLabel?: string, action?: () => void): void {
    const region = this.root.querySelector<HTMLElement>(".toast-region");
    if (!region) return;
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    const toast = element("div", "toast", element("span", "toast-mark", "MW"), element("p", "", message));
    if (actionLabel && action) {
      toast.append(textButton(actionLabel, "toast-action", () => {
        action();
        toast.remove();
      }));
    }
    region.replaceChildren(toast);
    this.toastTimer = window.setTimeout(() => toast.remove(), actionLabel ? 9000 : 5200);
  }

  private errorMessage(error: unknown): string {
    if (error instanceof Error) return error.message;
    return "发生未知错误";
  }
}
