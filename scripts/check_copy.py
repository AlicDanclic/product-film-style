#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕 / 解说词静态检查。

把 references/copy-style.md 里的规则变成可执行检查：字数、标点、禁用句式、
TTS 多音字、「的」结尾、中英混排空格。写文案时随手跑一遍，比人工复读快。

用法
----
    # 直接传
    python check_copy.py --text "任务字段自定义" --text "插件跑进 Worker"

    # 从一个文件读，一行一条，# 开头是注释
    python check_copy.py --file captions.txt

    # 只看结论、不要逐条明细
    python check_copy.py --file captions.txt --quiet

退出码：有 ERROR 返回 1，否则 0。WARN 不影响退出码。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 一级字幕的硬上限：超过 18 字基本不可能在 3–4 秒内读完
MAX_CJK = 12
HARD_MAX_CJK = 18

CJK = re.compile(r"[\u4e00-\u9fff]")
PUNCT = re.compile(r"[，。！？、：；「」『』（）《》…—]")

# 禁用句式：AI 写文案的指纹
BANNED = [
    (re.compile(r"不是.{0,12}而是"), "「不是…而是…」排比"),
    (re.compile(r"不仅仅.{0,12}更是"), "「不仅仅是…更是…」排比"),
    (re.compile(r"让我们"), "「让我们…」"),
    (re.compile(r"在这个时代|在当今|如今的社会"), "空转开场"),
    (re.compile(r"赋能|闭环|抓手|颗粒度|心智|范式|生态位"), "互联网黑话"),
    (re.compile(r"极致|丝滑|颠覆|重新定义|革命性"), "空洞形容词"),
    (re.compile(r"无需.{0,10}也能"), "凑排比"),
    (re.compile(r"(更快|更强|更好).{0,4}(更稳|更省|更自由|更简单)"), "三段式排比"),
    (re.compile(r"所以|这意味着|换句话说"), "多余连接词"),
]

# TTS 多音字：命中即建议换词，不靠标拼音
POLYPHONE = [
    ("行", "行/ háng·xíng：表格行→第 N 条，行业→领域"),
    ("重", "重/ chóng·zhòng：重新→再次，重命名→改名"),
    ("长", "长/ cháng·zhǎng：长按→按住"),
    ("还", "还/ hái·huán：还是→仍然"),
    ("便", "便/ biàn·pián：方便→容易"),
    ("得", "得/ dé·děi·de：得到→拿到"),
    ("着", "着/ zhe·zháo·zhuó：着手→开始做"),
    ("调", "调/ tiáo·diào：调整→改"),
    ("系", "系/ xì·jì：关系→关联"),
    ("载", "载/ zǎi·zài：记载→记录"),
    ("干", "干/ gān·gàn：干扰→影响"),
    ("差", "差/ chā·chà：差异→不同"),
    ("少", "少/ shǎo·shào：多少→几个"),
    ("薄", "薄/ báo·bó：薄片→片"),
    ("数", "数/ shù·shǔ：数据（多数引擎正确，仍建议试听）"),
]

SAFE_WORDS = ("长度", "必须", "加载", "数据")


def strip_safe(line: str) -> str:
    """去掉已知安全的词，避免误报。"""
    for w in SAFE_WORDS:
        line = line.replace(w, "")
    return line


def check(line: str) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    stripped = line.strip()
    n = len(CJK.findall(stripped))

    if n > HARD_MAX_CJK:
        issues.append(("ERROR", f"{n} 个汉字，超过 {HARD_MAX_CJK} 字的硬上限，必须拆段或删字"))
    elif n > MAX_CJK:
        issues.append(("WARN", f"{n} 个汉字，长于建议的 {MAX_CJK} 字，先怀疑文案写长了"))

    if PUNCT.search(stripped):
        issues.append(("WARN", "含中文标点；字幕是短语不是句子，标点一律去掉"))

    for pat, why in BANNED:
        if pat.search(stripped):
            issues.append(("ERROR", f"命中禁用句式：{why}"))

    for ch, hint in POLYPHONE:
        if ch in strip_safe(stripped):
            issues.append(("WARN", f"疑似 TTS 多音字「{ch}」——{hint}"))

    if stripped.endswith("的"):
        issues.append(("WARN", "以「的」结尾，通常是没写完的定语从句"))

    # 中英混排：中文与英文之间建议留一个空格
    if re.search(r"[\u4e00-\u9fff][A-Za-z]|[A-Za-z][\u4e00-\u9fff]", stripped):
        issues.append(("WARN", "中英之间缺空格（排版细节，统一后更好看）"))

    if re.search(r"[，。！？]", stripped) and stripped.endswith(("了", "呢", "吧", "吗")):
        issues.append(("WARN", "带语气词收尾，像口语句子；字幕用名词短语"))

    return issues


def load_lines(args) -> list[str]:
    lines: list[str] = []
    for t in args.text or []:
        lines.append(t)
    for f in args.file or []:
        p = Path(f)
        if not p.exists():
            sys.exit(f"文件不存在：{f}")
        for raw in p.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if s and not s.startswith("#"):
                lines.append(s)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="字幕 / 解说词静态检查")
    ap.add_argument("--text", action="append", help="一条文案，可重复")
    ap.add_argument("--file", action="append", help="文案文件，一行一条，# 为注释")
    ap.add_argument("--quiet", action="store_true", help="只输出统计与问题汇总")
    args = ap.parse_args()

    lines = load_lines(args)
    if not lines:
        sys.exit("没有输入。用 --text 或 --file 给至少一条文案。")

    errors = warns = 0
    detail: list[tuple[str, str, str]] = []

    for line in lines:
        issues = check(line)
        errs = [i for i in issues if i[0] == "ERROR"]
        wns = [i for i in issues if i[0] == "WARN"]
        errors += len(errs)
        warns += len(wns)
        if not args.quiet:
            n = len(CJK.findall(line))
            flag = " OK " if not issues else ("ERR  " if errs else "WARN ")
            print(f"[{flag}] {n:>2}字  {line}")
            for level, msg in issues:
                print(f"         {'x' if level == 'ERROR' else '!'} {msg}")
        for level, msg in issues:
            detail.append((level, line, msg))

    n_pass = sum(1 for line in lines if not check(line))
    print()
    print(f"共 {len(lines)} 条 · 干净 {n_pass} · 警告 {warns} · 错误 {errors}")

    if errors:
        print("\n必须先改的错误：")
        for level, line, msg in detail:
            if level == "ERROR":
                print(f"  · {line}  →  {msg}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
