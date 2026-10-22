"""Extract slide candidates from a local video; human review is mandatory.

This module never downloads platform links or calls an OCR/model service.
It preserves source times and crops, so a restored deck can be checked.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def crop_box(region, size):
    x, y, w, h = region
    if not (
        0 <= x < 1
        and 0 <= y < 1
        and 0 < w <= 1
        and 0 < h <= 1
        and x + w <= 1.000001
        and y + h <= 1.000001
    ):
        raise ValueError("课件区域应为 x,y,宽,高 四个 0–1 小数，且不得越过画面边缘")
    width, height = size
    box = (round(x * width), round(y * height), round((x + w) * width), round((y + h) * height))
    if box[2] - box[0] < 32 or box[3] - box[1] < 32:
        raise ValueError("课件区域过小")
    return box


def signature(frame, box):
    image = Image.fromarray(frame).crop(box).convert("L")
    return np.asarray(ImageOps.fit(image, (160, 90)), dtype=np.float32) / 255


def find_segments(clip, box, interval=1.0, threshold=0.065):
    if interval <= 0 or not 0 < threshold < 1:
        raise ValueError("采样间隔与变化阈值无效")
    if clip.duration <= 0:
        raise ValueError("视频没有可读取的时长")
    cuts, previous = [0.0], None
    for t in np.arange(0, clip.duration, interval):
        current = signature(clip.get_frame(float(t)), box)
        if previous is not None and float(np.abs(current - previous).mean()) >= threshold:
            if t - cuts[-1] >= interval:
                cuts.append(float(t))
        previous = current
    ends = cuts[1:] + [float(clip.duration)]
    return list(zip(cuts, ends, strict=True))


def extract(source: Path, destination: Path, region=(0, 0, 1, 1), interval=1.0, threshold=0.065):
    from moviepy import VideoFileClip

    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "manifest.json").exists():
        raise ValueError("目标目录已有提取结果，请另选目录，以免覆盖人工整理记录")
    with VideoFileClip(str(source)) as clip:
        if clip.duration > 7200:
            raise ValueError("请先按章节拆分超过两小时的视频")
        box = crop_box(region, clip.size)
        segments = find_segments(clip, box, interval, threshold)
        pages = []
        for index, (start, end) in enumerate(segments, 1):
            # End-of-segment frame captures completed progressive bullet reveals.
            at = max(start, end - min(0.35, (end - start) / 3))
            name = f"candidate-{index:03}.png"
            Image.fromarray(clip.get_frame(at)).crop(box).save(destination / name)
            pages.append(
                {
                    "candidate": index,
                    "start": start,
                    "end": end,
                    "frame_time": at,
                    "image": name,
                    "reviewed": False,
                    "transcription": None,
                }
            )
        with source.open("rb") as file:
            digest = (
                hashlib.file_digest(file, "sha256").hexdigest()
                if hasattr(hashlib, "file_digest")
                else None
            )
        manifest = {
            "source_name": source.name,
            "source_sha256": digest,
            "source_duration": clip.duration,
            "crop_pixels": list(box),
            "note": "候选截图，不是已校对的PPT。请合并重复页，逐页核对文字、图表和遮挡。",
            "pages": pages,
        }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="从本地视频提取课件候选截图及时间索引")
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--crop", default="0,0,1,1", help="课件区域 x,y,宽,高（0–1），建议排除人物和字幕"
    )
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--threshold", type=float, default=0.065)
    args = parser.parse_args()
    try:
        values = tuple(float(v) for v in args.crop.split(","))
        if len(values) != 4:
            raise ValueError("--crop 需要四个小数")
        result = extract(args.video, args.output, values, args.interval, args.threshold)
        print(f"已提取 {len(result['pages'])} 个候选页面，请检查 manifest.json 中的时间索引。")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
