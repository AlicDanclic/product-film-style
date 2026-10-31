/**
 * 产品宣传片 · 设计 token
 *
 * 与 references/visual-system.md 一一对应。新片直接拷进项目，只改 APP 尺寸。
 * 改这里的值等于改全片风格，别在场景文件里写死颜色。
 */

import type { CSSProperties } from 'react';

// ── 画布 ────────────────────────────────────────────────
export const FPS = 30;
export const DESIGN_FPS = 20; // 界面交互类镜头的设计时钟
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** 主内容左右内边距 */
export const GUTTER = 240;
/** 底部字幕带基线：任何卡片下沿都不能越过它 */
export const CAPTION_TOP = 966;
/** 卡片下沿安全线 */
export const SAFE_BOTTOM = 890;
/** 对照类双面板顶 */
export const DUAL_TOP = 222;

// ── 色彩 ────────────────────────────────────────────────
export const COLORS = {
  ink: '#17152B',
  text: '#111827',
  secondary: '#4B5563',
  muted: '#9CA3AF',
  indigo: '#4F46E5',
  indigoSoft: '#6366F1',
  violet: '#8B5CF6',
  pink: '#EC4899',
  surface: '#F3F4F6',
  sidebar: '#F9FAFB',
  border: '#E5E7EB',
  white: '#FFFFFF',
  green: '#10B981',
  amber: '#F59E0B',
  red: '#EF4444',
  blue: '#3B82F6',
} as const;

/** 语义色只表达语义，不许当装饰 */
export const SEMANTIC = {
  done: COLORS.green,
  doing: COLORS.amber,
  overdue: COLORS.red,
  info: COLORS.blue,
} as const;

// ── 渐变 ────────────────────────────────────────────────
export const GRADIENT = `linear-gradient(105deg, ${COLORS.indigo} 0%, ${COLORS.violet} 48%, ${COLORS.pink} 100%)`;
export const GRADIENT_SOFT =
  'linear-gradient(135deg, #EEF2FF 0%, #F5F3FF 52%, #FDF2F8 100%)';

/** 关键词渐变：只给词，不给句。一句话里最多两处 */
export const accentText = (): CSSProperties => ({
  backgroundImage: GRADIENT,
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  color: 'transparent',
});

// ── 字体 ────────────────────────────────────────────────
export const FONT_SANS =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif';

export const FONT_MONO =
  '"Cascadia Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace';

/** 字号阶梯，不含单位以外的换算 */
export const TYPE = {
  claim: { fontSize: 84, fontWeight: 800, letterSpacing: -4, lineHeight: 1.08 },
  sceneTitle: { fontSize: 56, fontWeight: 700, letterSpacing: -2, lineHeight: 1.15 },
  caption: { fontSize: 34, fontWeight: 700, letterSpacing: -0.5, lineHeight: 1.2 },
  panelTitle: { fontSize: 26, fontWeight: 700, letterSpacing: 0, lineHeight: 1.3 },
  body: { fontSize: 22, fontWeight: 500, letterSpacing: 0, lineHeight: 1.55 },
  note: { fontSize: 20, fontWeight: 500, letterSpacing: 0, lineHeight: 1.5 },
  meta: { fontSize: 22, fontWeight: 500, letterSpacing: 0, lineHeight: 1.4 },
} as const;

// ── 阴影 ────────────────────────────────────────────────
/** 阴影带紫、不带黑；靠大范围低透明度制造浮起，不用小半径黑影 */
export const SHADOW = {
  window:
    '0 44px 100px rgba(55, 48, 163, 0.14), 0 12px 30px rgba(55, 48, 163, 0.08), 0 0 0 1px rgba(79,70,229,0.07)',
  card: '0 18px 44px rgba(55, 48, 163, 0.10), 0 2px 8px rgba(55, 48, 163, 0.05)',
  pill: '0 12px 28px rgba(55, 48, 163, 0.08), 0 1px 2px rgba(55, 48, 163, 0.04)',
  lifted: '0 22px 48px rgba(55, 48, 163, 0.18), 0 4px 12px rgba(55, 48, 163, 0.08)',
} as const;

// ── 形状 ────────────────────────────────────────────────
export const RADIUS = { card: 18, panel: 14, pill: 999, chip: 8 } as const;

/** 产品窗口：按其自身尺寸设计内容，再整体放到画布上 */
export const APP = {
  width: 1480,
  height: 840,
  chromeHeight: 42,
  sidebarWidth: 218,
  radius: RADIUS.card,
} as const;

// ── 节拍 ────────────────────────────────────────────────
export const BEAT = {
  /** 词组 stagger，帧 */
  stagger: 12,
  /** 硬切段内容本地时间轴前移量（简单结构） */
  entry: 10,
  /** 复杂结构（图谱、表格、节点连线） */
  entryHeavy: 30,
  /** 注释行延迟淡入范围 */
  noteDelay: [34, 46] as const,
  /** 常驻浮动周期，秒 */
  floatPeriod: 3.5,
  /** 常驻浮动幅度，px */
  floatAmp: 5,
} as const;
