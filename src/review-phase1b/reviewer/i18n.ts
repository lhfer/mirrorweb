/**
 * Reviewer Mode is written for a careful person who is not a graphics
 * engineer. Chinese is the default language, English is available, and no
 * string may require the reader to know what a homography, a normalized
 * coordinate or a cumulative inward distance is.
 */

export type Language = "zh" | "en";

type Entry = { zh: string; en: string };

const TEXT = {
  appTitle: { zh: "Phase 1B 人工审查", en: "Phase 1B Human Review" },
  reviewerMode: { zh: "审查模式", en: "Reviewer Mode" },
  advancedInspector: { zh: "高级检视器", en: "Advanced Inspector" },
  openAdvanced: { zh: "打开高级检视器（技术数值）", en: "Open Advanced Inspector (technical values)" },
  backToReviewer: { zh: "返回审查模式", en: "Back to Reviewer Mode" },
  language: { zh: "语言", en: "Language" },

  saveIdle: { zh: "草稿已同步", en: "Draft in sync" },
  saveSaving: { zh: "保存中…", en: "Saving…" },
  saveSaved: { zh: "已保存", en: "Saved" },
  saveFailed: { zh: "保存失败", en: "Save failed" },
  saveRetry: { zh: "重试保存", en: "Retry save" },
  autosaveHint: {
    zh: "每次修改都会自动保存为草稿。刷新页面会回到同一个角色与同一步骤。",
    en: "Every change is autosaved as a draft. Reloading returns to the same role and step.",
  },

  roleQueue: { zh: "审查队列", en: "Review queue" },
  tutorialEntry: { zh: "教程：先看这个", en: "Tutorial: start here" },
  tutorialBadge: { zh: "不计入 7 个角色", en: "Not one of the 7 roles" },
  roleHeader: { zh: "角色", en: "Role" },
  stepHeader: { zh: "步骤", en: "Step" },

  statePendingFrame: { zh: "待选择画面", en: "Pending frame" },
  statePendingQuad: { zh: "待确认卡片范围", en: "Pending quad" },
  statePendingZones: { zh: "待标记光学分区", en: "Pending zones" },
  statePendingLock: { zh: "待锁定", en: "Pending lock" },
  stateLocked: { zh: "目标已锁定", en: "Target locked" },
  stateRejected: { zh: "已否决", en: "Rejected" },

  step1Title: { zh: "第 1 步 · 选择目标画面", en: "Step 1 · Choose the target frame" },
  step2Title: { zh: "第 2 步 · 确认卡片范围", en: "Step 2 · Confirm the card quad" },
  step3Title: { zh: "第 3 步 · 标记光学分区", en: "Step 3 · Mark the optical zones" },
  step4Title: { zh: "第 4 步 · 锁定目标标注", en: "Step 4 · Lock the target annotation" },
  step5Title: { zh: "第 5 步 · 与本地结果对比", en: "Step 5 · Compare against local" },

  step1Lead: {
    zh: "只看目标视频的画面。判断这一帧能不能用来标注，不需要和本地结果比较。",
    en: "Look only at the target video frame. Decide whether this frame can be annotated at all.",
  },
  step2Lead: {
    zh: "把四个角拖到卡片真实的外轮廓上。右侧会实时显示拉平后的卡片。",
    en: "Drag the four corners onto the real outline of the card. The flattened card updates live on the right.",
  },
  step3Lead: {
    zh: "在卡片上直接拖动三条边界。百分比由拖动结果自动算出，不需要你输入数字。",
    en: "Drag the three boundaries directly on the card. Percentages are derived from the drag, never typed.",
  },
  step4Lead: {
    zh: "确认下面的摘要。锁定之后这个目标标注变为只读，需要解锁才能修改。",
    en: "Check the summary. After locking, this target annotation becomes read-only until you unlock it.",
  },
  step5Lead: {
    zh: "现在才显示本地结果。本步骤的结论不会改变已锁定的目标标注。",
    en: "The local capture appears only now. Nothing here changes the locked target annotation.",
  },

  sourceFrame: { zh: "完整画面", en: "Full source frame" },
  selectedCard: { zh: "自动提取的卡片预览", en: "Selected card preview" },
  candidateStrip: { zh: "候选画面", en: "Candidate frames" },
  candidatePrimary: { zh: "自动选中", en: "Auto-selected" },
  candidateMissing: {
    zh: "候选画面尚未生成。运行 npm run v4:review:candidates 之后可以选择更干净的画面。",
    en: "Candidate frames are not built yet. Run npm run v4:review:candidates to pick a cleaner frame.",
  },
  acceptFrame: { zh: "接受这一帧", en: "Accept frame" },
  rejectFrame: { zh: "否决这一帧", en: "Reject frame" },
  chooseAnother: { zh: "换一帧", en: "Choose another frame" },
  rejectReasonTitle: { zh: "否决原因（可多选）", en: "Rejection reasons (multiple allowed)" },
  confirmReject: { zh: "确认否决", en: "Confirm rejection" },
  cancel: { zh: "取消", en: "Cancel" },
  alternateFrameWarning: {
    zh: "你选择了自动选中之外的画面。这个标注会被标记为需要重新固定 Frozen 帧，不会自动覆盖现有绑定。",
    en: "You picked a frame other than the auto-selected one. The annotation is flagged for re-pinning and never silently rebinds.",
  },

  reasonMotionBlur: { zh: "运动模糊", en: "Motion blur" },
  reasonCursor: { zh: "光标遮挡", en: "Cursor occlusion" },
  reasonHighlight: { zh: "高光遮挡", en: "Highlight occlusion" },
  reasonClipped: { zh: "卡片被裁切", en: "Card clipped" },
  reasonWrongRole: { zh: "不是这个角色的画面", en: "Wrong role" },
  reasonUnclear: { zh: "边界看不清", en: "Boundary unclear" },

  acceptQuad: { zh: "接受卡片范围", en: "Accept card quad" },
  resetQuad: { zh: "重置卡片范围", en: "Reset quad" },
  rectifiedCard: { zh: "拉平后的卡片", en: "Rectified card plane" },
  zoomLabel: { zh: "放大", en: "Zoom" },
  loupeHint: { zh: "拖动角点时会显示局部放大镜。", en: "A loupe appears while you drag a corner." },
  cornerTL: { zh: "左上", en: "Top left" },
  cornerTR: { zh: "右上", en: "Top right" },
  cornerBR: { zh: "右下", en: "Bottom right" },
  cornerBL: { zh: "左下", en: "Bottom left" },
  coverageLabel: { zh: "卡片占审查区域", en: "Card fills review area" },

  acceptZones: { zh: "接受光学分区", en: "Accept optical zones" },
  resetZones: { zh: "重置分区", en: "Reset zones" },
  boundaryUnclear: { zh: "边界看不清", en: "Boundary unclear" },
  zoneCenter: { zh: "中心面", en: "Center face" },
  zoneShoulder: { zh: "光学肩部", en: "Optical shoulder" },
  zoneRim: { zh: "强透镜边缘", en: "Strong lens rim" },
  zoneSidewall: { zh: "侧壁", en: "Sidewall" },
  zoneCenterHelp: { zh: "内容基本稳定，几乎不变形。", en: "Content is basically stable, almost undistorted." },
  zoneShoulderHelp: { zh: "内容开始缓慢弯曲。", en: "Content starts to bend slowly." },
  zoneRimHelp: { zh: "内容快速压缩、折叠，可能出现局部色散。", en: "Content compresses and folds fast; local dispersion may appear." },
  zoneSidewallHelp: { zh: "最外层侧壁和反射区域。", en: "The outermost sidewall and reflection band." },
  viewWhole: { zh: "整张卡片", en: "Whole card" },
  viewTop: { zh: "上边", en: "Top edge" },
  viewRight: { zh: "右边", en: "Right edge" },
  viewBottom: { zh: "下边", en: "Bottom edge" },
  viewLeft: { zh: "左边", en: "Left edge" },
  viewCornerTL: { zh: "左上角", en: "TL corner" },
  viewCornerTR: { zh: "右上角", en: "TR corner" },
  viewCornerBR: { zh: "右下角", en: "BR corner" },
  viewCornerBL: { zh: "左下角", en: "BL corner" },
  derivedPercent: { zh: "自动算出的宽度", en: "Derived widths" },
  dragHint: { zh: "把三条线拖到内容变化开始的位置。", en: "Drag each line to where the content behaviour changes." },

  lockButton: { zh: "锁定目标标注", en: "Lock target annotation" },
  unlockButton: { zh: "解锁并修改", en: "Unlock to edit" },
  unlockReasonPrompt: { zh: "解锁原因（至少 8 个字符）", en: "Unlock reason (at least 8 characters)" },
  lockedNotice: { zh: "目标标注已锁定，当前为只读。", en: "This target annotation is locked and read-only." },
  annotationHash: { zh: "标注指纹", en: "Annotation hash" },
  summaryFrame: { zh: "目标画面", en: "Target frame" },
  summaryQuad: { zh: "卡片四角", en: "Card quad" },
  summaryZones: { zh: "四个光学分区", en: "Four optical zones" },
  summaryEdges: { zh: "四边裁切", en: "Edge crops" },
  summaryCorners: { zh: "四角裁切", en: "Corner crops" },

  compareTarget: { zh: "目标", en: "Target" },
  compareLocal: { zh: "本地", en: "Local" },
  compareOverlay: { zh: "50% 叠加", en: "50% overlay" },
  overlayEdge: { zh: "边缘", en: "Edge" },
  overlayHighlight: { zh: "高光", en: "Highlight" },
  overlayDispersion: { zh: "色散", en: "Dispersion" },
  overlaySharpness: { zh: "锐度", en: "Sharpness" },
  compareVerdictTitle: { zh: "本地结果的判断（不影响目标标注）", en: "Local verdict (does not affect the target annotation)" },
  verdictClose: { zh: "本地接近", en: "Local looks close" },
  verdictTooWide: { zh: "本地边缘过宽", en: "Local too wide" },
  verdictTooNarrow: { zh: "本地边缘过窄", en: "Local too narrow" },
  verdictDirection: { zh: "折射方向不对", en: "Wrong refraction direction" },
  verdictHighlight: { zh: "高光不匹配", en: "Highlight mismatch" },
  verdictDispersion: { zh: "色散不匹配", en: "Dispersion mismatch" },
  verdictLater: { zh: "留待后续复核", en: "Needs later review" },
  compareNote: { zh: "备注", en: "Note" },
  noSsimNotice: {
    zh: "本步骤只按四边和四角一一对应地比较，不做整卡相似度打分。",
    en: "This step compares matching edges and corners only; there is no whole-card similarity score.",
  },

  showExample: { zh: "查看示例", en: "Show example" },
  hideExample: { zh: "收起示例", en: "Hide example" },
  exampleCorrect: { zh: "正确示例", en: "Correct" },
  exampleWrong: { zh: "常见错误", en: "Common mistake" },
  exampleJudgeTitle: { zh: "这一步需要判断", en: "This step asks you to judge" },
  exampleSkipTitle: { zh: "这一步不需要判断", en: "This step does not ask you to judge" },

  tutorialTitle: { zh: "开始之前：五分钟看懂要标什么", en: "Before you start: what you are marking" },
  tutorialSynthetic: { zh: "示意图（合成）", en: "Schematic (synthetic)" },
  tutorialReal: { zh: "真实目标画面示例", en: "Real target example" },
  tutorialOutline: { zh: "外轮廓", en: "Outer silhouette" },
  tutorialOutlineHelp: { zh: "卡片本身的边，不是它周围的光晕。", en: "The card's own edge, not the glow around it." },
  tutorialNotBoundary: { zh: "以下都不能当作边界", en: "None of these is a boundary" },
  notHighlight: { zh: "高光条", en: "Specular highlight" },
  notHalo: { zh: "光晕 / Halo", en: "Halo" },
  notDispersion: { zh: "色散最外缘", en: "Outermost dispersion fringe" },
  notTypography: { zh: "卡片上的文字", en: "Typography on the card" },
  notInnerBorder: { zh: "视频内部的边框", en: "Inner border inside the video" },
  notNeighbour: { zh: "相邻的另一张卡片", en: "An adjacent card" },
  tutorialStart: { zh: "我明白了，开始审查", en: "Got it, start reviewing" },
  tutorialReopen: { zh: "重看教程", en: "Reopen tutorial" },
  tutorialNoWrite: { zh: "教程不会写入任何标注。", en: "The tutorial writes no annotation." },

  targetOnlyBadge: { zh: "目标标注阶段 · 本地结果已隐藏", en: "Target annotation stage · local hidden" },
  localVisibleBadge: { zh: "对比阶段 · 已显示本地结果", en: "Compare stage · local visible" },
  next: { zh: "下一步", en: "Next" },
  back: { zh: "上一步", en: "Back" },
  blockedTitle: { zh: "审查界面未就绪", en: "Review surface is not ready" },
  blockedRetry: { zh: "重新绑定", en: "Retry binding" },
  loading: { zh: "载入中…", en: "Loading…" },
} as const satisfies Record<string, Entry>;

export type TextKey = keyof typeof TEXT;

let current: Language = "zh";

export function setLanguage(language: Language): void {
  current = language;
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
}

export function language(): Language {
  return current;
}

export function t(key: TextKey): string {
  return TEXT[key][current];
}

/** Both languages at once, for labels that stay technical on purpose. */
export function bilingual(key: TextKey): string {
  return current === "zh" ? `${TEXT[key].zh} / ${TEXT[key].en}` : TEXT[key].en;
}
