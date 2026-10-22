"""Internal end-to-end check. This is NOT a reconstruction of any reference video."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_workflow.models import Avatar, Project, RenderOptions, Slide
from video_workflow.storage import Store
from video_workflow.video import font_path, render_project


def main():
    import argparse

    parser = argparse.ArgumentParser(description="实际语音和视频编码自测，非参考视频复刻")
    parser.add_argument("--character", type=Path, required=True)
    args = parser.parse_args()
    store = Store(Path("data"))
    project = Project(
        title="程序自测（非参考视频内容）",
        status="ready",
        avatar=Avatar(image="avatar/otter.png", mouth=(0.48, 0.19, 0.15, 0.035)),
        slides=[
            Slide(
                title="中文配音与换角色测试",
                image="slides/page-001.png",
                source_page=1,
                narration="这是一段程序自测。我们正在验证中文配音、角色嘴型和课件合成。",
            )
        ],
    )
    store.save(project)
    root = store.directory(project.id)
    (root / "slides").mkdir()
    (root / "avatar").mkdir()
    import shutil

    shutil.copyfile(args.character, root / "avatar" / "otter.png")
    page = Image.new("RGB", (1280, 720), "#eef3ef")
    draw = ImageDraw.Draw(page)
    title = ImageFont.truetype(font_path(), 54)
    body = ImageFont.truetype(font_path(), 30)
    draw.text((75, 130), "中文配音与换角色测试", font=title, fill="#213d49")
    draw.text((75, 280), "程序自测页面", font=body, fill="#3d6a67")
    draw.text((75, 355), "非参考视频 PPT 内容", font=body, fill="#6a8184")
    page.save(root / project.slides[0].image)
    outputs = render_project(project, root, RenderOptions(width=1280, height=720, fps=24), print)
    project.outputs = outputs
    project.output_version = project.version
    project.progress = "自测完成"
    store.save(project)
    print(root / outputs["video"])


if __name__ == "__main__":
    main()
