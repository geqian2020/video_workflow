import asyncio
import hashlib
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cue:
    start: float
    end: float
    text: str


def sentences(text: str) -> list[str]:
    """Keep punctuation and every character; timing follows actual generated audio."""
    return [
        part.strip()
        for part in re.findall(r"[^。！？!?\n]+[。！？!?]?|[^\n]", text)
        if part.strip()
    ]


def _sapi(text: str, dest: Path):
    if os.name != "nt":
        raise ValueError("离线中文语音目前需要 Windows；其他系统请选择在线中文语音")
    from .windows import run_powershell

    textfile = dest.with_suffix(".txt")
    textfile.write_text(text, encoding="utf-8-sig")
    try:
        result = run_powershell(
            "speak.ps1",
            {
                "WORKFLOW_TEXT_FILE": str(textfile.resolve()),
                "WORKFLOW_OUTPUT_WAVE": str(dest.resolve()),
            },
            timeout=120,
        )
        if result.returncode or not dest.exists():
            raise ValueError("离线语音生成失败。请确认安装了 Windows 简体中文语音包。")
    finally:
        textfile.unlink(missing_ok=True)


def _edge(text: str, dest: Path):
    import edge_tts
    from moviepy import AudioFileClip

    mp3 = dest.with_suffix(".mp3")
    voice = os.environ.get("VIDEO_WORKFLOW_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
    try:

        async def request():
            await asyncio.wait_for(edge_tts.Communicate(text, voice).save(str(mp3)), timeout=120)

        asyncio.run(request())
        with AudioFileClip(str(mp3)) as audio:
            audio.write_audiofile(
                str(dest), fps=16000, codec="pcm_s16le", ffmpeg_params=["-ac", "1"], logger=None
            )
    except Exception as exc:
        raise ValueError("在线配音失败，请检查网络或改用 Windows 离线配音。") from exc
    finally:
        mp3.unlink(missing_ok=True)


def synthesize(text: str, cache: Path, engine: str) -> tuple[Path, list[Cue]]:
    parts = sentences(text)
    if not parts:
        raise ValueError("请先填写这一页的讲稿")
    cache.mkdir(parents=True, exist_ok=True)
    voice = os.environ.get("VIDEO_WORKFLOW_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
    key = hashlib.sha256(f"v2-normalized\0{engine}\0{voice}\0{text}".encode()).hexdigest()[:24]
    output = cache / f"{key}.wav"
    cues, buffers = [], []
    position, signature = 0.0, None
    for part in parts:
        digest = hashlib.sha256(f"v1\0{engine}\0{voice}\0{part}".encode()).hexdigest()[:24]
        chunk = cache / f"chunk-{digest}.wav"
        if not chunk.exists():
            temporary = chunk.with_name(f"{chunk.stem}.part.wav")
            try:
                (_sapi if engine == "sapi" else _edge)(part, temporary)
                # Validate before publishing the cache entry.
                with wave.open(str(temporary), "rb") as file:
                    if file.getnframes() == 0:
                        raise ValueError("配音引擎返回了空音频")
                os.replace(temporary, chunk)
            finally:
                temporary.unlink(missing_ok=True)
        with wave.open(str(chunk), "rb") as file:
            shape = (file.getnchannels(), file.getsampwidth(), file.getframerate())
            if signature is not None and signature != shape:
                raise ValueError("配音音频格式不一致，请清理这个项目的语音缓存后重试")
            signature = shape
            duration = file.getnframes() / file.getframerate()
            buffers.append(file.readframes(file.getnframes()))
        cues.append(Cue(position, position + duration, part))
        position += duration
        if position > 600:
            raise ValueError("单页配音超过 10 分钟，请把内容拆成多页")
    if not output.exists():
        from moviepy import AudioFileClip

        temporary = output.with_name(output.stem + ".part.wav")
        raw = output.with_name(output.stem + ".raw.wav")
        with wave.open(str(raw), "wb") as file:
            file.setnchannels(signature[0])
            file.setsampwidth(signature[1])
            file.setframerate(signature[2])
            file.writeframes(b"".join(buffers))
        try:
            with AudioFileClip(str(raw)) as audio:
                audio.write_audiofile(
                    str(temporary),
                    fps=16000,
                    codec="pcm_s16le",
                    ffmpeg_params=["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1"],
                    logger=None,
                )
            os.replace(temporary, output)
        finally:
            raw.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
    return output, cues


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    sec, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{sec:02},{milliseconds:03}"


def write_srt(cues: list[Cue], output: Path):
    output.write_text(
        "\n\n".join(
            f"{i}\n{srt_timestamp(c.start)} --> {srt_timestamp(c.end)}\n{c.text}"
            for i, c in enumerate(cues, 1)
        )
        + "\n",
        encoding="utf-8-sig",
    )
