import math
import os
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import Avatar, Project, RenderOptions
from .speech import Cue, synthesize, write_srt


def font_path() -> str:
    configured = os.environ.get("VIDEO_WORKFLOW_FONT")
    candidates = [
        configured,
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise ValueError("缺少中文字体，请设置 VIDEO_WORKFLOW_FONT 为中文字体文件路径")


def envelope(path: Path, fps: int) -> np.ndarray:
    with wave.open(str(path), "rb") as file:
        if file.getsampwidth() != 2:
            raise ValueError("嘴型分析需要 16 位 PCM 音频")
        rate = file.getframerate()
        data = np.frombuffer(file.readframes(file.getnframes()), dtype="<i2").astype(float)
        channels = file.getnchannels()
        data = data.reshape(-1, channels).mean(axis=1) / 32768
    step = rate / fps
    rms = np.array(
        [
            np.sqrt(np.mean(data[int(i * step) : int((i + 1) * step)] ** 2))
            for i in range(math.ceil(len(data) / step))
        ]
    )
    if len(rms) == 0 or rms.max() < 0.0001:
        return np.zeros(max(1, len(rms)))
    peak = max(float(np.percentile(rms, 90)), 0.001)
    result = np.clip(rms / peak, 0, 1)
    result[rms < max(peak * 0.09, 0.001)] = 0
    return result


def caption_lines(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, current = [], ""
    for char in text:
        if char == "\n" or font.getlength(current + char) > width:
            if current:
                lines.append(current)
            current = "" if char == "\n" else char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def display_cues(cues: list[Cue], width: int, font: ImageFont.FreeTypeFont) -> list[Cue]:
    result = []
    for cue in cues:
        lines = caption_lines(cue.text, font, width)
        pages = ["\n".join(lines[i : i + 2]) for i in range(0, len(lines), 2)]
        total = sum(len(text.replace("\n", "")) for text in pages) or 1
        start = cue.start
        for index, text in enumerate(pages):
            duration = (cue.end - cue.start) * len(text.replace("\n", "")) / total
            end = cue.end if index == len(pages) - 1 else start + duration
            result.append(Cue(start, end, text))
            start = end
    return result


def avatar_frame(image: Image.Image, avatar: Avatar, openness: float) -> Image.Image:
    """Deterministic amplitude mouth overlay, explicitly labelled as basic animation."""
    frame = image.copy()
    if openness > 0:
        x, y, w, h = avatar.mouth
        x, y, w, h = x * frame.width, y * frame.height, w * frame.width, h * frame.height
        radius = max(1, h * openness / 2)
        draw = ImageDraw.Draw(frame)
        draw.ellipse((x - w / 2, y - radius, x + w / 2, y + radius), fill="#4b2535")
        if openness > 0.45:
            draw.ellipse(
                (x - w * 0.22, y + radius * 0.15, x + w * 0.22, y + radius * 0.7), fill="#ef9b9e"
            )
    return frame


def make_frame_renderer(
    slide_path: Path,
    avatar_path: Path,
    avatar: Avatar,
    options: RenderOptions,
    cues: list[Cue],
    env: np.ndarray,
):
    width, height = options.width, options.height
    vertical = height > width
    background = Image.new("RGB", (width, height), "#f5f4ef")
    with Image.open(slide_path) as original:
        slide = original.convert("RGB")
    # Reserve real space for the presenter rather than covering slide content.
    box = (
        (round(width * 0.92), round(height * 0.52))
        if vertical
        else (round(width * 0.71), round(height * 0.77))
    )
    slide = ImageOps.contain(slide, box, Image.Resampling.LANCZOS)
    sx = (width - slide.width) // 2 if vertical else round(width * 0.035)
    sy = round(height * 0.07) + (box[1] - slide.height) // 2
    background.paste(slide, (sx, sy))
    with Image.open(avatar_path) as source:
        character = source.convert("RGBA")
    bbox = character.getbbox()
    if bbox is None:
        raise ValueError("角色图片完全透明")
    # Keep full-image coordinates so the mouth marker remains valid.
    maxsize = (
        (round(width * 0.40), round(height * 0.23))
        if vertical
        else (round(width * 0.23), round(height * min(0.72, avatar.size * 2.18)))
    )
    character = ImageOps.contain(character, maxsize, Image.Resampling.LANCZOS)
    ax = (width - character.width) // 2 if vertical else round(width * 0.875 - character.width / 2)
    ay = (
        round(height * 0.84 - character.height)
        if vertical
        else round(height * 0.83 - character.height)
    )
    fsize = round(height * (0.022 if vertical else 0.034))
    font = ImageFont.truetype(font_path(), max(18, fsize))
    visible = display_cues(cues, round(width * 0.86), font)
    # Quantised mouth states avoid redrawing the character artwork per frame.
    sprites = [avatar_frame(character, avatar, n / 7) for n in range(8)]

    def frame(t: float):
        canvas = background.copy().convert("RGBA")
        index = min(len(env) - 1, max(0, int(t * options.fps)))
        level = float(env[index]) if len(env) else 0
        sprite = sprites[min(7, round(level * 7))]
        # Smooth bounded idle movement, with zero random state or cumulative drift.
        shift = round(2 * math.sin(t * 1.25))
        canvas.alpha_composite(sprite, (ax, ay + shift))
        active = next((cue.text for cue in visible if cue.start <= t < cue.end), "")
        if active:
            draw = ImageDraw.Draw(canvas)
            lines = active.splitlines()
            lineheight = max(24, round(font.size * 1.45))
            y = height - round(height * 0.09) - (len(lines) - 1) * lineheight
            for line in lines:
                draw.text(
                    (width / 2, y),
                    line,
                    font=font,
                    fill="#18242e",
                    anchor="mm",
                    stroke_width=1,
                    stroke_fill="#f5f4ef",
                )
                y += lineheight
        return np.asarray(canvas.convert("RGB"))

    return frame


def render_project(project: Project, root: Path, options: RenderOptions, progress):
    from uuid import uuid4

    from moviepy import AudioFileClip, VideoClip, VideoFileClip, concatenate_videoclips

    if project.avatar is None:
        raise ValueError("请先上传卡通角色并标记嘴部位置")
    selection = options.slide_ids
    if selection is not None and (not selection or len(set(selection)) != len(selection)):
        raise ValueError("预览页面选择无效")
    if selection is not None and set(selection) - {s.id for s in project.slides}:
        raise ValueError("预览选择包含不存在的页面")
    slides = [s for s in project.slides if selection is None or s.id in selection]
    if not slides:
        raise ValueError("没有可渲染的页面")
    if any(not s.narration.strip() for s in slides):
        raise ValueError("所选页面中有空讲稿，请填写后再导出")
    run = root / "output" / uuid4().hex
    run.mkdir(parents=True)
    clips, all_cues, timeline = [], [], []
    position = 0.0
    try:
        for i, slide in enumerate(slides):
            progress(f"第 {i + 1}/{len(slides)} 页：生成中文配音")
            audio, cues = synthesize(slide.narration, root / "audio", options.engine)
            with AudioFileClip(str(audio)) as audio_clip:
                duration = audio_clip.duration + 0.20
                if position + duration > 3600:
                    raise ValueError("首版单次导出限制为 60 分钟，请按章节拆分")
                env = envelope(audio, options.fps)
                frame = make_frame_renderer(
                    root / slide.image,
                    root / project.avatar.image,
                    project.avatar,
                    options,
                    cues,
                    env,
                )
                output = run / f"page-{i + 1:03}.mp4"
                progress(f"第 {i + 1}/{len(slides)} 页：合成角色和字幕")
                with VideoClip(frame_function=frame, duration=duration) as video:
                    voiced = video.with_audio(audio_clip)
                    try:
                        voiced.write_videofile(
                            str(output),
                            fps=options.fps,
                            codec="libx264",
                            audio_codec="aac",
                            preset="fast",
                            threads=2,
                            logger=None,
                        )
                    finally:
                        voiced.close()
            timeline.append(
                {
                    "slide_id": slide.id,
                    "source_page": slide.source_page,
                    "start": position,
                    "end": position + duration,
                    "audio": audio.relative_to(root).as_posix(),
                    "narration": slide.narration,
                    "caption_precision": "sentence",
                }
            )
            all_cues.extend(Cue(c.start + position, c.end + position, c.text) for c in cues)
            position += duration
            clips.append(output)
        progress("合并视频并保存时间线")
        opened = []
        final = None
        try:
            for path in clips:
                opened.append(VideoFileClip(str(path)))
            final = concatenate_videoclips(opened, method="chain")
            final.write_videofile(
                str(run / "presentation.mp4"),
                fps=options.fps,
                codec="libx264",
                audio_codec="aac",
                preset="fast",
                threads=2,
                logger=None,
            )
        finally:
            if final is not None:
                final.close()
            for clip in opened:
                clip.close()
        write_srt(all_cues, run / "subtitles.srt")
        import json

        (run / "timeline.json").write_text(
            json.dumps(
                {
                    "version": project.version,
                    "width": options.width,
                    "height": options.height,
                    "fps": options.fps,
                    "avatar_animation": "audio_amplitude",
                    "slides": timeline,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "video": (run / "presentation.mp4").relative_to(root).as_posix(),
            "subtitles": (run / "subtitles.srt").relative_to(root).as_posix(),
            "timeline": (run / "timeline.json").relative_to(root).as_posix(),
        }
    finally:
        # Only remove this run's intermediate page files, never user originals.
        for clip in clips:
            clip.unlink(missing_ok=True)
