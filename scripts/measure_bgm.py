#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BGM 换曲时的响度对齐计算。

换背景音乐时最容易犯的错：把旧曲的音量峰值直接套到新曲上。两首曲子的母带响度
差 1–2 dB 很常见，套用旧值会让整片忽大忽小。这个脚本按 ebur128 实测，算出「要和
旧曲听感一致，峰值该填多少」。

关键点：**必须测实际用到的那一段，不是整轨**。同一首歌前 60 秒与整轨能差 0.5 dB
以上，而片子只用开头。

用法
----
    # 旧曲基准：-16.6 LUFS 时峰值用 0.22；新曲要匹配这个听感
    python measure_bgm.py --track public/sunset.mp3 \\
        --windows 120,66 --baseline-lufs -16.6 --base-volume 0.22

    # 只想知道一首曲子各段的响度
    python measure_bgm.py --track public/day-beetle.mp3 --windows 120,66

    # 首尾淡入淡出会拉低整体响度，只想测中间稳态段
    python measure_bgm.py --track cut.mp3 --windows 120 --skip 15

输出每个窗口的 LUFS、真实峰值、与基准的差值、增益系数，以及建议填进代码的峰值。
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def measure(path: Path, seconds: float | None, skip: float) -> dict | None:
    cmd = ["ffmpeg", "-nostats", "-hide_banner"]
    if skip:
        cmd += ["-ss", f"{skip}"]
    if seconds:
        cmd += ["-t", f"{seconds}"]
    cmd += ["-i", str(path), "-map", "a:0", "-af", "ebur128=peak=true", "-f", "null", "-"]
    cp = run(cmd)
    text = cp.stderr
    if "Integrated loudness" not in text:
        return None
    out: dict[str, float] = {}
    for key, pat in (
        ("lufs", r"I:\s+(-?\d+\.\d+)\s+LUFS"),
        ("lra", r"LRA:\s+(-?\d+\.\d+)\s+LU"),
        ("true_peak", r"Peak:\s+(-?\d+\.\d+)\s+dBFS"),
    ):
        found = re.findall(pat, text)
        if found:
            out[key] = float(found[-1])
    return out or None


def probe_duration(path: Path) -> float | None:
    cp = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(cp.stdout.strip())
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="BGM 换曲响度对齐计算")
    ap.add_argument("--track", required=True, type=Path, help="音频或视频文件")
    ap.add_argument("--windows", default="",
                    help="要测的时长窗口（秒），逗号分隔，对应片子实际用到的长度；留空测整轨")
    ap.add_argument("--skip", type=float, default=0.0, help="跳过开头若干秒（避开淡入段）")
    ap.add_argument("--baseline-lufs", type=float,
                    help="旧曲在同一窗口下的实测响度（换曲基准）")
    ap.add_argument("--base-volume", required=False, default="",
                    help="旧曲在基准响度下使用的音量峰值；多个窗口可给逗号分隔的多个值，"
                         "如 0.22,0.20（主片 0.22 / 短片 0.20）")
    ap.add_argument("--peak-ceiling", type=float, default=-1.0,
                    help="换算后真峰上限 dBFS，超过则提示降低峰值，默认 -1.0")
    args = ap.parse_args()

    if not args.track.exists():
        sys.exit(f"文件不存在：{args.track}")
    if not shutil.which("ffmpeg"):
        sys.exit("找不到 ffmpeg")
    base_volumes = [float(x) for x in args.base_volume.replace(" ", "").split(",") if x != ""]
    if args.baseline_lufs is not None and not base_volumes:
        sys.exit("给了 --baseline-lufs 就必须同时给 --base-volume")

    total = probe_duration(args.track)
    windows = [float(x) for x in args.windows.replace(" ", "").split(",") if x != ""] or [None]

    print(f"\n曲目  {args.track.name}" + (f"（{total:.1f}s）" if total else ""))
    if args.baseline_lufs is not None:
        print(f"基准  旧曲 {args.baseline_lufs} LUFS 时峰值取 {', '.join(f'{v:g}' for v in base_volumes)}")
    print()

    header = f"{'窗口':>10} {'LUFS':>9} {'LRA':>7} {'真峰':>8} {'差值':>8} {'增益':>8}  建议峰值"
    print(header)
    print("-" * (len(header) + 10))

    rows = []
    for w in windows:
        stats = measure(args.track, w, args.skip)
        if not stats or "lufs" not in stats:
            print(f"{('整轨' if w is None else f'{w:g}s'):>10}   —— 测不到音轨")
            continue
        label = "整轨" if w is None else f"{w:g}s"
        lufs = stats["lufs"]
        if args.baseline_lufs is None:
            print(f"{label:>10} {lufs:>9.1f} {stats.get('lra', 0):>7.1f} "
                  f"{stats.get('true_peak', 0):>8.1f} {'':>8} {'':>8}  -")
            rows.append({"window": w, "lufs": lufs})
            continue

        idx = len(rows) if len(rows) < len(base_volumes) else -1
        base = base_volumes[idx]
        delta = args.baseline_lufs - lufs           # 需要补多少 dB
        gain = 10 ** (delta / 20)
        peak = round(base * gain, 4)
        # gain 只是「相对基准的修正系数」，成片真正听到的峰值是 真峰 × 最终音量
        out_peak = stats.get("true_peak", 0) + 20 * math.log10(peak)
        warn = ""
        if out_peak > args.peak_ceiling:
            safe = peak * 10 ** ((args.peak_ceiling - out_peak) / 20)
            warn = f"  ↑成片真峰将达 {out_peak:+.1f} dBFS，超上限 → 峰值压到 {safe:.3f}"
        print(f"{label:>10} {lufs:>9.1f} {stats.get('lra', 0):>7.1f} "
              f"{stats.get('true_peak', 0):>8.1f} {delta:>+8.2f} {gain:>8.3f}  {peak}{warn}")
        rows.append({"window": w, "lufs": lufs, "base": base, "gain": round(gain, 4),
                     "peak": peak, "out_true_peak": round(out_peak, 1)})

    print()
    if args.baseline_lufs is not None and rows:
        peaks = {r["peak"] for r in rows if "peak" in r}
        if len(peaks) == 1:
            print(f"结论  所有窗口折算一致，峰值统一填 {peaks.pop()}")
        elif peaks:
            print("结论  各窗口折算不同，按片段分别填：")
            for r in rows:
                if "peak" in r:
                    label = "整轨" if r["window"] is None else f"{r['window']:g}s 片段"
                    print(f"      · {label}（基准 {r['base']:g}）→ {r['peak']}")
    else:
        print("提示  加上 --baseline-lufs 与 --base-volume 即可算出该填的音量峰值")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
