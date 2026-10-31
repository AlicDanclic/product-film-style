#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成片审稿：规格 / 切点空帧 / 音轨响度。

对应 SKILL.md 的「审稿三步」中的第 3 步（切点测试），并顺带核对规格与响度。

用法
----
    python audit_film.py --video out/film.mp4 --fps 30 \
        --cutpoints 0,150,400,640,880,1200,1560,1840

    # 不给切点就按等距切片猜（知道段数更好）
    python audit_film.py --video out/film.mp4 --fps 30 --segments 8

    # 片头首帧与落版淡入属已知例外，豁免之
    python audit_film.py --video out/film.mp4 --fps 30 \
        --cutpoints 0,150,400,1840 --allow 0,1840

    # 顺带核对成片音轨响度是否偏离预期
    python audit_film.py --video out/film.mp4 --fps 30 --cutpoints 0,150 --expect-lufs -30.6

判定分级
--------
OK     切点帧已有内容
GROW   切点帧只有背景，但 1.6 秒内长出来了——叙事片可接受，快节奏片应视为缺陷
EMPTY  切点帧只有背景，且 1.6 秒后仍然是空的（真缺陷）
WHITE  整帧接近纯白；BLACK 整帧接近纯黑

默认 GROW 放行，它抓的是「一直空着」这类真缺陷；加 --strict 则 GROW 也判不合格，
用于对比片 / 密集演示片——那类片子切点空白一眼就能看出闪。

判定逻辑
--------
不给绝对阈值（不同片子白度不同），而是先等距抽若干「参考帧」，取内容密度的中位数
作基线，再逐个切点与基线比。低于基线 35% 判 EMPTY——即「这一帧基本只剩背景和
一个空壳」。这个相对判定对白底片、深色片同样成立。

依赖：ffmpeg / ffprobe 在 PATH 中，Python 侧需要 numpy + Pillow。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 numpy 与 Pillow：pip install numpy pillow")

EMPTY_RATIO = 0.35  # 切点内容密度 / 参考中位数 的判空下限
WHITE_LUM = 0.985
BLACK_LUM = 0.020
BOX = 17  # 局部反差窗口（像素），约等于一个汉字的尺度
GROW_WINDOW = 48  # 判「生长式入场」的后看窗口（帧），约 1.6 秒


# ---------------------------------------------------------------- ffmpeg 探测

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(video: Path) -> dict:
    cp = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,codec_name",
        "-show_entries", "format=duration,size",
        "-of", "json", str(video),
    ])
    if cp.returncode != 0:
        sys.exit(f"ffprobe 失败：{cp.stderr.strip()}")
    data = json.loads(cp.stdout)
    st = data["streams"][0]
    num, _, den = st["r_frame_rate"].partition("/")
    fps = float(num) / float(den or 1)
    duration = float(data["format"]["duration"])
    nb = st.get("nb_frames")
    return {
        "width": st["width"],
        "height": st["height"],
        "fps": fps,
        "codec": st["codec_name"],
        "duration": duration,
        "nb_frames": int(nb) if nb and nb.isdigit() else round(duration * fps),
        "size_mb": round(int(data["format"]["size"]) / 1048576, 1),
    }


# ---------------------------------------------------------------- 抽帧

def extract_frames(video: Path, frame_ids: list[int], outdir: Path) -> dict[int, Path]:
    """一次性抽完所有目标帧，用 -frame_pts 让文件名就是原始帧号。"""
    expr = "+".join(f"eq(n\\,{n})" for n in sorted(set(frame_ids)))
    cp = run([
        "ffmpeg", "-v", "error", "-i", str(video),
        "-vf", f"select='{expr}'",
        "-vsync", "vfr", "-frame_pts", "1",
        str(outdir / "f%06d.png"),
    ])
    if cp.returncode != 0:
        sys.exit(f"抽帧失败：{cp.stderr.strip()}")
    return {int(p.stem.lstrip("f")): p for p in outdir.glob("f*.png")}


# ---------------------------------------------------------------- 帧内容密度

def box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """积分图实现的方框模糊，O(n)，不依赖 scipy。"""
    pad = k // 2
    p = np.pad(a, pad, mode="edge")
    ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    h, w = a.shape
    s = ii[k:k + h, k:k + w] - ii[0:h, k:k + w] - ii[k:k + h, 0:w] + ii[0:h, 0:w]
    return s / (k * k)


def frame_stats(path: Path) -> dict:
    img = Image.open(path).convert("L")
    g = np.asarray(img, dtype=np.float32) / 255.0
    mean_lum = float(g.mean())

    # 局部反差：像素与自身邻域均值的偏离程度。文字、线条、图标会显著抬高它，
    # 而平滑渐变背景与空白卡片几乎为 0。
    local = np.abs(g - box_blur(g, BOX))
    contrast = float((local > 0.012).mean())

    # 边缘密度作为交叉验证：空壳只剩卡片边框，条纹极少。
    gx = np.abs(np.diff(g, axis=1))
    gy = np.abs(np.diff(g, axis=0))
    edge = float(((gx > 0.02).mean() + (gy > 0.02).mean()) / 2)

    return {"lum": mean_lum, "contrast": contrast, "edge": edge}


# ---------------------------------------------------------------- 音轨响度

def measure_lufs(video: Path, window: float | None) -> dict | None:
    cmd = ["ffmpeg", "-nostats", "-hide_banner"]
    if window:
        cmd += ["-t", f"{window}"]
    cmd += ["-i", str(video), "-map", "a:0", "-af", "ebur128=peak=true", "-f", "null", "-"]
    cp = run(cmd)
    text = cp.stderr
    if "Integrated loudness" not in text:
        return None
    out: dict[str, float] = {}
    for label, pat in (
        ("lufs", r"I:\s+(-?\d+\.\d+)\s+LUFS"),
        ("lra", r"LRA:\s+(-?\d+\.\d+)\s+LU"),
        ("true_peak", r"Peak:\s+(-?\d+\.\d+)\s+dBFS"),
    ):
        found = re.findall(pat, text)
        if found:
            out[label] = float(found[-1])
    return out or None


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="成片审稿：规格 / 切点空帧 / 响度")
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--fps", type=float, help="不给则读容器")
    ap.add_argument("--cutpoints", help="切点帧号，逗号分隔，如 0,150,400")
    ap.add_argument("--segments", type=int, help="不知道切点就按段数等分猜")
    ap.add_argument("--ref-count", type=int, default=9, help="参考帧数量")
    ap.add_argument("--allow", default="", help="豁免帧号，逗号分隔（片头首帧、落版淡入起点等）")
    ap.add_argument("--expect-lufs", type=float,
                    help="预期成片音轨响度；偏离超过 1.5 dB 判警告。注意这里比的是成片音轨，"
                         "不是原始曲目——原始曲目换增益请用 measure_bgm.py")
    ap.add_argument("--grow-window", type=int, default=GROW_WINDOW,
                    help=f"后看窗口（帧），默认 {GROW_WINDOW} 帧 ≈ 1.6 秒；窄于真实入场时长会误判为 EMPTY")
    ap.add_argument("--strict", action="store_true",
                    help="把 GROW（切点空白但随后长出内容）也判为不合格，对比片 / 密集演示片用")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非表格")
    args = ap.parse_args()

    allow = {int(x) for x in args.allow.replace(" ", "").split(",") if x != ""}

    if not args.video.exists():
        sys.exit(f"文件不存在：{args.video}")
    if not shutil.which("ffmpeg"):
        sys.exit("找不到 ffmpeg")

    info = probe(args.video)
    fps = args.fps or info["fps"]
    total = info["nb_frames"]

    if args.cutpoints:
        cutpoints = [int(x) for x in args.cutpoints.replace(" ", "").split(",") if x != ""]
    elif args.segments:
        cutpoints = [round(i * total / args.segments) for i in range(args.segments)]
    else:
        cutpoints = [0]
    cutpoints = [min(max(c, 0), total - 1) for c in cutpoints]

    # 参考帧：等距取，跳过切点自身，用来建立「有内容」的基线
    guard = {c + d for c in cutpoints for d in (-1, 0, 1, 2)}
    refs = [
        round(i * (total - 1) / (args.ref_count + 1)) + 1
        for i in range(1, args.ref_count + 1)
    ]
    refs = [r for r in refs if r not in guard][: args.ref_count] or [total // 2]

    tmp = Path(tempfile.mkdtemp(prefix="audit_film_"))
    try:
        # 先抽切点与参考帧，判出可疑切点后再补抽「后看帧」，避免白抽一堆。
        frames = extract_frames(args.video, cutpoints + refs, tmp)
        missing = [n for n in cutpoints + refs if n not in frames]
        if missing:
            sys.exit(f"抽帧不完整，缺帧号 {missing[:5]}（可能超出实际帧数）")

        ref_stats = {n: frame_stats(frames[n]) for n in refs}
        ref_median = float(np.median([s["contrast"] for s in ref_stats.values()]))
        threshold = ref_median * EMPTY_RATIO

        # 第一轮：只看切点帧本身
        cut_stats: dict[int, dict] = {n: frame_stats(frames[n]) for n in cutpoints}
        suspects = [
            n for n in cutpoints
            if cut_stats[n]["lum"] < WHITE_LUM and cut_stats[n]["lum"] > BLACK_LUM
            and cut_stats[n]["contrast"] < threshold
        ]

        # 第二轮：对可疑切点往后看，区分「空壳」与「生长式入场」
        grow_steps = sorted({8, 16, 24, args.grow_window})
        grow_frames: dict[int, int] = {}
        if suspects:
            lookahead = [n + d for n in suspects for d in grow_steps if n + d < total]
            more = extract_frames(args.video, lookahead, tmp) if lookahead else {}
            for n in suspects:
                for d in grow_steps:
                    f = frames.get(n + d) or more.get(n + d)
                    if f and frame_stats(f)["contrast"] >= threshold:
                        grow_frames[n] = d
                        break

        rows = []
        for n in cutpoints:
            s = cut_stats[n]
            ratio = s["contrast"] / ref_median if ref_median > 0 else 0.0
            grow = grow_frames.get(n)
            if s["lum"] >= WHITE_LUM:
                verdict = "WHITE"
            elif s["lum"] <= BLACK_LUM:
                verdict = "BLACK"
            elif ratio < EMPTY_RATIO:
                verdict = "GROW" if grow else "EMPTY"
            else:
                verdict = "OK"
            if n in allow and verdict != "OK":
                verdict += "*"
            rows.append({
                "frame": n,
                "t": round(n / fps, 3),
                "contrast": round(s["contrast"], 5),
                "edge": round(s["edge"], 5),
                "lum": round(s["lum"], 4),
                "ratio": round(ratio, 3),
                "grow_after": grow,
                "verdict": verdict,
                "allowed": n in allow,
            })

        audio = measure_lufs(args.video, None)
        audio_note = None
        if audio and args.expect_lufs is not None and "lufs" in audio:
            delta = audio["lufs"] - args.expect_lufs
            audio_note = {"delta_db": round(delta, 2), "ok": abs(delta) <= 1.5}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failing = {"EMPTY", "WHITE", "BLACK"} | ({"GROW"} if args.strict else set())
    bad = [r for r in rows if r["verdict"].rstrip("*") in failing and not r["allowed"]]
    exempt = [r for r in rows if r["allowed"] and r["verdict"] != "OK"]
    growing = [r for r in rows if r["verdict"].rstrip("*") == "GROW" and not r["allowed"]]

    if args.json:
        print(json.dumps(
            {"video": str(args.video), "spec": info, "reference_median": round(ref_median, 5),
             "cutpoints": rows, "audio": audio, "audio_check": audio_note,
             "passed": not bad},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"\n成片  {args.video.name}")
        print(f"规格  {info['width']}x{info['height']} @ {fps:g}fps · "
              f"{total} 帧 · {info['duration']:.3f}s · {info['size_mb']} MB · {info['codec']}")
        print(f"基线  参考帧内容密度中位数 = {ref_median:.5f}（{len(refs)} 帧等距采样）\n")
        head = (f"{'帧号':>7} {'时间':>8} {'内容密度':>10} {'边缘':>8} {'亮度':>7} "
                f"{'占比':>6} {'长出':>5}  判定")
        print(head)
        print("-" * len(head))
        for r in rows:
            mark = ""
            if r["verdict"].rstrip("*") in failing and not r["allowed"]:
                mark = "  <-- 检查"
            elif r["allowed"] and r["verdict"] != "OK":
                mark = "  (已豁免)"
            elif r["verdict"].rstrip("*") == "GROW":
                mark = "  (生长式入场)"
            grow = f"+{r['grow_after']}f" if r.get("grow_after") else "-"
            print(f"{r['frame']:>7} {r['t']:>7.2f}s {r['contrast']:>10.5f} "
                  f"{r['edge']:>8.5f} {r['lum']:>7.4f} {r['ratio']:>6.2f} {grow:>5}  "
                  f"{r['verdict']}{mark}")
        if audio:
            print(f"\n音轨  整体 {audio.get('lufs')} LUFS · LRA {audio.get('lra')} LU · "
                  f"真峰 {audio.get('true_peak')} dBFS")
        if audio_note:
            n, flag = audio_note, "正常" if audio_note["ok"] else "偏差过大"
            print(f"核对  与预期 {args.expect_lufs} LUFS 相差 {n['delta_db']:+.2f} dB → {flag}")
        print()
        if growing and not args.strict:
            print(f"生长  {len(growing)} 个切点切在空白上、随后长出内容："
                  f"{', '.join(str(r['frame']) for r in growing)}")
            print(f"      叙事片可接受（背景连续，观众读作「内容浮现」）；"
                  f"对比片 / 密集演示片应加 --strict")
        if exempt:
            print(f"豁免  {len(exempt)} 个切点按例外放行（片头首帧 / 落版淡入属有意留白）")
        if bad:
            print(f"结果  {len(bad)} 个切点不合格：")
            for r in bad:
                reason = {
                    "EMPTY": f"内容密度不足，且后续 {args.grow_window} 帧内没有长出内容",
                    "WHITE": "整帧接近纯白，白屏",
                    "BLACK": "整帧接近纯黑，黑屏",
                    "GROW": "切点落在空白上（--strict 模式）",
                }[r["verdict"].rstrip("*")]
                if r["frame"] == 0:
                    print(f"      · 第 0 帧{reason}；若是片头从无到有，用 --allow 0 豁免")
                elif r["verdict"].rstrip("*") == "GROW":
                    print(f"      · 第 {r['frame']} 帧（{r['t']:.2f}s）{reason} → "
                          f"把该段内容的时间轴前移 {r['grow_after'] or 10} 帧")
                else:
                    print(f"      · 第 {r['frame']} 帧（{r['t']:.2f}s）{reason} → "
                          f"把该段内容的时间轴前移 10–30 帧")
        else:
            print(f"结果  全部切点通过")

    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
