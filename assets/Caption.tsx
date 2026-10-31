/**
 * 产品宣传片 · 字幕带与小注释
 *
 * 全片文字只有两类：
 *   Caption  —— 每段一行短语，跟着硬切一起满、一起消失，**不做淡入淡出**
 *   NoteLine —— 右下角小注释，延迟 34–46 帧才淡入，避免切点后只剩一行小字像故障
 *
 * 用法：
 *   <Caption>任务字段自定义</Caption>
 *   <NoteLine delay={40}>空白处横向拖一下，就多一条</NoteLine>
 */

import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { CAPTION_TOP, COLORS, FONT_MONO, TYPE } from './tokens';

type CaptionProps = {
  children: React.ReactNode;
  /** 水平对齐，默认居中；左对齐适合与左侧面板对齐的片子 */
  align?: 'center' | 'left';
  /** 段末淡出用，0–1 的透明度系数；硬切段落不要传 */
  fade?: number;
};

export const Caption: React.FC<CaptionProps> = ({ children, align = 'center', fade = 1 }) => (
  <AbsoluteFill style={{ pointerEvents: 'none' }}>
    <div
      style={{
        position: 'absolute',
        top: CAPTION_TOP,
        left: align === 'center' ? 0 : 240,
        right: align === 'center' ? 0 : 240,
        textAlign: align,
        fontFamily: 'inherit',
        ...TYPE.caption,
        color: 'rgba(23, 21, 43, 0.86)',
        opacity: fade,
        // 字幕永远不换行：换行说明文案写长了，去删字，不要调字号
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </div>
  </AbsoluteFill>
);

type NoteLineProps = {
  children: React.ReactNode;
  /** 延迟帧，34–46 之间取值；同一段内多条注释可错开 */
  delay?: number;
  /** 淡入时长，帧 */
  duration?: number;
  align?: 'right' | 'left';
};

export const NoteLine: React.FC<NoteLineProps> = ({
  children,
  delay = 40,
  duration = 14,
  align = 'right',
}) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(1, Math.max(0, (frame - delay) / duration));

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          bottom: 64,
          left: align === 'left' ? 240 : undefined,
          right: align === 'right' ? 240 : undefined,
          ...TYPE.note,
          color: COLORS.muted,
          opacity,
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};

type MetaLineProps = {
  children: React.ReactNode;
  /** 落版用：等宽、弱化色 */
};

/** 落版底部的地址行：等宽字体、弱化色、不抢标题 */
export const MetaLine: React.FC<MetaLineProps> = ({ children }) => (
  <div
    style={{
      fontFamily: FONT_MONO,
      ...TYPE.meta,
      color: '#6F7281',
      marginTop: 24,
      letterSpacing: 0,
    }}
  >
    {children}
  </div>
);
