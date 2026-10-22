from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Slide(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    content: list[str] = Field(default_factory=list)
    narration: str = Field(default="", max_length=8000)
    image: str
    source_page: int


class Avatar(BaseModel):
    image: str = "avatar/character.png"
    # Fractions of the character image: centre x, centre y, width, height.
    mouth: tuple[float, float, float, float] = (0.5, 0.55, 0.12, 0.06)
    size: float = Field(default=0.33, ge=0.15, le=0.55)

    @model_validator(mode="after")
    def validate_mouth(self):
        x, y, w, h = self.mouth
        if not (0 < w <= 0.6 and 0 < h <= 0.4):
            raise ValueError("嘴部宽高超出范围")
        if not (w / 2 <= x <= 1 - w / 2 and h / 2 <= y <= 1 - h / 2):
            raise ValueError("嘴部区域必须位于角色图片内")
        return self


BUSY = {"importing", "generating", "rendering", "previewing"}


class Project(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "新建讲解"
    source_name: str = ""
    source_kind: Literal["pptx", "pdf", "generated"] = "pdf"
    status: str = "importing"
    progress: str = "准备导入"
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    version: int = 1
    output_version: int | None = None
    preview_version: int | None = None
    preview_audio_slide: str | None = None
    slides: list[Slide] = Field(default_factory=list)
    avatar: Avatar | None = None
    outputs: dict[str, str] = Field(default_factory=dict)


class SlideEdit(BaseModel):
    narration: str = Field(max_length=8000)
    title: str = Field(max_length=300)


class Generation(BaseModel):
    content: str = Field(min_length=10, max_length=20000)
    slides: int = Field(default=6, ge=2, le=20)
    title: str = Field(default="文案生成的演示文稿", max_length=150)
    template: str = Field(default="general", pattern=r"^[\w-]{1,60}$")


class RenderOptions(BaseModel):
    width: int = Field(default=1280, ge=640, le=1920, multiple_of=2)
    height: int = Field(default=720, ge=360, le=1920, multiple_of=2)
    fps: int = Field(default=24, ge=12, le=30)
    engine: Literal["sapi", "edge"] = "sapi"
    # Omit to render all slides. IDs avoid page-order ambiguity.
    slide_ids: list[str] | None = None
