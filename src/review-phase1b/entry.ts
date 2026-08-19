/**
 * Entry point for the private Phase 1B review page.
 *
 * Reviewer Mode is the default surface. The original dense inspector is kept
 * verbatim as the Advanced Inspector and is only mounted when it is explicitly
 * requested, so its markup, its module and its behaviour stay unchanged.
 */

const advanced = new URLSearchParams(window.location.search).get("mode") === "advanced";

async function mountAdvanced(): Promise<void> {
  const template = document.querySelector<HTMLTemplateElement>("#advanced-inspector");
  if (!template) throw new Error("Advanced Inspector markup is missing");
  document.body.append(template.content.cloneNode(true));
  document.body.dataset.mode = "advanced";
  const link = document.createElement("a");
  link.className = "advanced-back-link";
  link.href = "?";
  link.textContent = "← Reviewer Mode / 审查模式";
  document.querySelector(".topbar")?.append(link);
  await import("./main");
}

async function mountReviewer(): Promise<void> {
  document.body.dataset.mode = "reviewer";
  await import("./reviewer/app");
}

void (advanced ? mountAdvanced() : mountReviewer()).catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  const node = document.createElement("pre");
  node.style.cssText = "color:#ef684d;font:13px/1.5 monospace;padding:24px";
  node.textContent = `Phase 1B review failed to start: ${message}`;
  document.body.append(node);
});
