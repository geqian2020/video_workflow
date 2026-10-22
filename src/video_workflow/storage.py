import json
import os
import re
import threading
from pathlib import Path

from .models import BUSY, Project, now


class Store:
    """Atomic project files; one server process and one writer per project."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def directory(self, project_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", project_id):
            raise FileNotFoundError("项目不存在")
        return self.root / project_id

    def save(self, project: Project) -> Project:
        with self.lock:
            folder = self.directory(project.id)
            folder.mkdir(parents=True, exist_ok=True)
            project.updated_at = now()
            tmp = folder / "project.json.tmp"
            tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, folder / "project.json")
        return project

    def load(self, project_id: str) -> Project:
        with self.lock:
            path = self.directory(project_id) / "project.json"
            return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Project]:
        projects = []
        with self.lock:
            for path in self.root.glob("*/project.json"):
                try:
                    projects.append(Project.model_validate_json(path.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    continue
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def update(self, project_id: str, **changes) -> Project:
        with self.lock:
            project = self.load(project_id)
            for key, value in changes.items():
                setattr(project, key, value)
            return self.save(project)

    def recover(self):
        for project in self.list():
            if project.status in BUSY:
                self.update(
                    project.id,
                    status="failed",
                    progress="任务中断，可重试",
                    error="上次运行意外结束。已经保存的素材和讲稿仍然保留。",
                )

    def asset(self, project_id: str, relative: str) -> Path:
        folder = self.directory(project_id)
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise FileNotFoundError("文件不存在")
        return path

    def manifest(self, project: Project) -> dict:
        result = json.loads(project.model_dump_json())
        result["output_stale"] = (
            "video" in project.outputs and project.output_version != project.version
        )
        result["preview_stale"] = (
            "preview_video" in project.outputs and project.preview_version != project.version
        )
        return result
