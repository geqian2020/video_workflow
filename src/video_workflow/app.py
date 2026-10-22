import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .decks import import_deck
from .models import BUSY, Avatar, Generation, Project, RenderOptions, SlideEdit
from .storage import Store

log = logging.getLogger(__name__)
MAX_UPLOAD = 150 * 1024 * 1024


async def save_upload(upload: UploadFile, path: Path, limit: int = MAX_UPLOAD):
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "文件过大，请压缩或拆分后上传")
                out.write(chunk)
        if not size:
            raise HTTPException(400, "上传文件为空")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = Store(data_dir or Path(os.environ.get("VIDEO_WORKFLOW_DATA", "data")))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-workflow")

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="卡通讲解工作台", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get(
                "host"
            ):
                return JSONResponse({"detail": "只允许从本地工作台提交操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": "项目或文件不存在"}, status_code=404)

    def idle(project: Project):
        if project.status in BUSY:
            raise HTTPException(409, "任务正在进行，请等待完成后再修改")

    def launch(project_id: str, status: str, task):
        with store.lock:
            project = store.load(project_id)
            idle(project)
            store.update(project_id, status=status, progress="任务已排队", error=None)

        def run():
            try:
                task()
            except Exception as exc:
                log.exception("Project %s failed", project_id)
                detail = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "任务失败，请查看本地服务日志后重试"
                )
                store.update(project_id, status="failed", progress="任务未完成", error=detail)

        executor.submit(run)
        return store.manifest(store.load(project_id))

    def imported(project_id: str, source: Path):
        root = store.directory(project_id)
        store.update(project_id, progress="导出页面并提取讲稿")
        slides, warnings = import_deck(source, root)
        store.update(
            project_id,
            slides=slides,
            warnings=warnings,
            status="ready",
            progress="已导入，请核对逐页讲稿",
            error=None,
        )

    @app.get("/api/config")
    def config():
        return {
            "presenton": bool(os.environ.get("PRESENTON_URL")),
            "narration_model": bool(
                os.environ.get("WORKFLOW_LLM_URL") and os.environ.get("WORKFLOW_LLM_MODEL")
            ),
            "offline_voice": os.name == "nt",
            "max_pages": 60,
            "default_engine": os.environ.get(
                "VIDEO_WORKFLOW_TTS", "sapi" if os.name == "nt" else "edge"
            ),
        }

    @app.get("/api/projects")
    def projects():
        return [store.manifest(p) for p in store.list()]

    @app.post("/api/projects", status_code=202)
    async def upload_deck(file: Annotated[UploadFile, File()]):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pptx", ".pdf"}:
            await file.close()
            raise HTTPException(400, "请上传 PPTX 或 PDF 文件")
        project = Project(
            title=Path(file.filename).stem[:150],
            source_name=Path(file.filename).name,
            source_kind=suffix[1:],
            status="new",
        )
        store.save(project)
        source = store.directory(project.id) / "source" / f"source{suffix}"
        try:
            await save_upload(file, source)
        except Exception:
            store.update(project.id, status="failed", error="文件上传未完成")
            raise
        return launch(project.id, "importing", lambda: imported(project.id, source))

    @app.post("/api/generate", status_code=202)
    def generate(body: Generation):
        from .generation import generate_deck, presenton_config

        try:
            presenton_config()
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        project = store.save(Project(title=body.title, source_kind="generated", status="new"))

        def task():
            root = store.directory(project.id)
            store.update(project.id, progress="根据文案生成 PPT")
            pptx, pdf = generate_deck(body, root / "source")
            slides, warnings = import_deck(pdf, root)
            from slide_stream.powerpoint import parse_powerpoint

            metadata = parse_powerpoint(pptx)
            current = store.load(project.id)
            current.slides, current.warnings = slides, warnings
            if len(metadata) == len(current.slides):
                for slide, data in zip(current.slides, metadata, strict=True):
                    slide.title = data["title"]
                    slide.content = data["content"]
                    slide.narration = (data["notes"] or "\n".join(data["content"]))[:8000]
            current.outputs.update(deck="source/source.pptx", pdf="source/source.pdf")
            current.status, current.progress = "ready", "PPT 已生成，请核对页面和讲稿"
            store.save(current)

        return launch(project.id, "generating", task)

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        return store.manifest(store.load(project_id))

    @app.post("/api/projects/{project_id}/retry-import", status_code=202)
    def retry_import(project_id: str):
        project = store.load(project_id)
        if project.slides:
            raise HTTPException(409, "项目已有页面，请新建项目重新导入，避免覆盖已编辑的讲稿")
        if project.source_kind == "generated":
            raise HTTPException(400, "请重新提交文案生成任务")
        source = store.asset(project_id, f"source/source.{project.source_kind}")
        return launch(project_id, "importing", lambda: imported(project_id, source))

    @app.patch("/api/projects/{project_id}/slides/{slide_id}")
    def edit_slide(project_id: str, slide_id: str, body: SlideEdit):
        with store.lock:
            current = store.load(project_id)
            idle(current)
            slide = next((s for s in current.slides if s.id == slide_id), None)
            if slide is None:
                raise HTTPException(404, "页面不存在")
            if slide.narration != body.narration or slide.title != body.title:
                if slide.narration != body.narration and current.preview_audio_slide == slide_id:
                    current.outputs.pop("preview_audio", None)
                    current.preview_audio_slide = None
                slide.narration, slide.title = body.narration, body.title
                current.version += 1
            return store.manifest(store.save(current))

    @app.post("/api/projects/{project_id}/avatar")
    async def upload_avatar(project_id: str, file: Annotated[UploadFile, File()]):
        from uuid import uuid4

        current = store.load(project_id)
        idle(current)
        relative = f"avatar/{uuid4().hex}.png"
        path = store.directory(project_id) / relative
        await save_upload(file, path, 15 * 1024 * 1024)
        try:
            with Image.open(path) as source:
                if source.width * source.height > 16_000_000:
                    raise ValueError("角色图片分辨率过大，请缩小到 4096 像素以内")
                image = source.convert("RGBA")
                if image.getbbox() is None:
                    raise ValueError("角色图片完全透明")
                opaque = image.getchannel("A").getextrema()[0] == 255
                image.save(path, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(
                400, str(exc) if isinstance(exc, ValueError) else "无法读取角色图片"
            ) from exc
        with store.lock:
            current = store.load(project_id)
            idle(current)
            current.avatar = Avatar(image=relative)
            current.version += 1
            if opaque:
                warning = "角色没有透明背景，视频会保留它的图片底色。建议上传透明 PNG。"
                if warning not in current.warnings:
                    current.warnings.append(warning)
            return store.manifest(store.save(current))

    @app.patch("/api/projects/{project_id}/avatar")
    def edit_avatar(project_id: str, body: Avatar):
        with store.lock:
            current = store.load(project_id)
            idle(current)
            if current.avatar is None:
                raise HTTPException(400, "请先上传角色")
            # The client may edit geometry, never the server-side file location.
            body.image = current.avatar.image
            if current.avatar != body:
                current.avatar = body
                current.version += 1
            return store.manifest(store.save(current))

    @app.post("/api/projects/{project_id}/slides/{slide_id}/narration", status_code=202)
    def draft_narration(project_id: str, slide_id: str):
        from .generation import write_narration

        current = store.load(project_id)
        selected = next((s for s in current.slides if s.id == slide_id), None)
        if selected is None:
            raise HTTPException(404, "页面不存在")

        def task():
            text = write_narration(selected.title, selected.content, selected.narration)
            current = store.load(project_id)
            next(s for s in current.slides if s.id == slide_id).narration = text
            if current.preview_audio_slide == slide_id:
                current.outputs.pop("preview_audio", None)
                current.preview_audio_slide = None
            current.version += 1
            current.status, current.progress = "ready", "讲稿已起草，请核对后配音"
            store.save(current)

        return launch(project_id, "generating", task)

    @app.post("/api/projects/{project_id}/preview/{slide_id}", status_code=202)
    def preview(project_id: str, slide_id: str, options: RenderOptions):
        from .speech import synthesize

        current = store.load(project_id)
        selected = next((s for s in current.slides if s.id == slide_id), None)
        if selected is None:
            raise HTTPException(404, "页面不存在")

        def task():
            audio, _ = synthesize(
                selected.narration, store.directory(project_id) / "audio", options.engine
            )
            current = store.load(project_id)
            current.outputs["preview_audio"] = audio.relative_to(
                store.directory(project_id)
            ).as_posix()
            current.preview_audio_slide = slide_id
            current.status, current.progress = "ready", "试听已生成"
            store.save(current)

        return launch(project_id, "previewing", task)

    @app.post("/api/projects/{project_id}/render", status_code=202)
    def render(project_id: str, options: RenderOptions):
        from .video import render_project

        current = store.load(project_id)
        if current.avatar is None:
            raise HTTPException(400, "请先上传卡通角色")

        def task():
            snapshot = store.load(project_id)
            outputs = render_project(
                snapshot,
                store.directory(project_id),
                options,
                lambda text: store.update(project_id, progress=text),
            )
            current = store.load(project_id)
            if options.slide_ids is not None:
                current.outputs.update({"preview_" + key: value for key, value in outputs.items()})
                current.preview_version = snapshot.version
                current.progress = "页面预览已生成"
            else:
                current.outputs.update(outputs)
                current.output_version = snapshot.version
                current.progress = "完整视频已生成"
            current.status = "ready"
            store.save(current)

        return launch(project_id, "rendering", task)

    @app.get("/api/projects/{project_id}/files/{relative:path}")
    def asset(project_id: str, relative: str):
        # Serve only generated media and the exact exported timeline.
        project = store.load(project_id)
        allowed = {s.image for s in project.slides} | set(project.outputs.values())
        if project.avatar:
            allowed.add(project.avatar.image)
        if relative not in allowed:
            raise HTTPException(404, "文件不存在")
        path = store.asset(project_id, relative)
        return FileResponse(path, filename=path.name, content_disposition_type="inline")

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    return app
