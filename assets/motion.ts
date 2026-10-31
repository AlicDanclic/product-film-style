/**
 * 产品宣传片 · 动效原语
 *
 * 四种动作，全片只用这四种，不做别的花样：
 *   入场 entry  —— spring + 上浮 + 微翻转
 *   退场 exit   —— 上飘 + 微翻转 + 淡到 10%
 *   常驻 float  —— sin 上下浮动，入场 settle 之后才启动
 *   节拍 beat   —— 统一 stagger，不按元素各调一套
 *
 * 另外两个约束写在代码里：所有 interpolate 必须 clamp；任何进入 inputRange
 * 的值都必须是有限数（用 NEVER 而不是 Infinity）。
 */

import type { CSSProperties } from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

/** interpolate 不接受 Infinity，用它表示「永远不触发」 */
export const NEVER = 1_000_000;

export const clampRamp = (
  input: number,
  range: [number, number],
  output: [number, number] = [0, 1],
): number =>
  interpolate(input, range, output, { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

/** 词组节拍：第 index 组的起始帧 */
export const beatStart = (index: number, step = 12): number => index * step;

/** 入场进度：spring 阻尼偏大、无回弹，产品片不要 bouncy */
export const useEnter = (delay = 0, config = { damping: 200, mass: 0.9, stiffness: 90 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config });
};

/** 入场的视觉层：上浮 40–70px + 绕 X 翻转 7°，父容器需 perspective(1500px) */
export const enterStyle = (
  progress: number,
  opts: { rise?: number; tilt?: boolean } = {},
): CSSProperties => {
  const { rise = 56, tilt = true } = opts;
  return {
    opacity: clampRamp(progress, [0, 0.55]),
    transform: [
      `translateY(${(1 - progress) * rise}px)`,
      tilt ? `rotateX(${(1 - progress) * 7}deg)` : null,
    ]
      .filter(Boolean)
      .join(' '),
  };
};

/** 退场的视觉层：上飘 + 微翻转 + 淡到 10% */
export const exitStyle = (progress: number, opts: { rise?: number } = {}): CSSProperties => {
  const { rise = 44 } = opts;
  return {
    opacity: 1 - progress * 0.9,
    transform: `translateY(${-progress * rise}px) rotateX(${-progress * 4}deg)`,
  };
};

/**
 * 退场的例外：当退场元素会与后续大字位置重叠时，必须彻底淡到 0。
 * 否则两层文字叠印，比闪一下更难修。
 */
export const exitStyleHard = (progress: number): CSSProperties => ({
  opacity: 1 - progress,
  transform: `translateY(${-progress * 30}px)`,
});

/**
 * 常驻浮动：只在入场 settle 之后调用，别和入场叠在一起。
 *
 * 这是纯函数，fps 显式传入——不要在里面调 useVideoConfig()，
 * 那样它就变成了 hook，容易被在非组件里误用。
 */
export const floatY = (
  frame: number,
  fps: number,
  amp = 5,
  periodSeconds = 3.5,
  phase = 0,
): number => Math.sin((frame / (fps * periodSeconds)) * Math.PI * 2 + phase) * amp;

/** 字幕/标题的淡入淡出一律不要；这里只提供「硬切」用的常量 */
export const NO_FADE = 1;

/**
 * 硬切段落的时间基准。
 *
 * 段内所有入场动画不要从本地第 0 帧起算，否则切点那一帧就是空的。
 * 把本地帧整体前移：简单结构 +10，图谱/表格/节点连同连线 +22~30。
 */
export const useCutFrame = (entry = 10): number => useCurrentFrame() + entry;

/**
 * 20fps 设计、30fps 播放。
 *
 * 界面交互类镜头（拖拽、勾选、连线）以 DESIGN_FPS 为设计时钟写动画，
 * 放进主片时用 playbackRate 换算，动作时长与 GIF 版完全一致。
 *   <Sequence playbackRate={DESIGN_FPS / FPS} ...>
 */
export const designPlaybackRate = (designFps: number, filmFps: number): number =>
  designFps / filmFps;
