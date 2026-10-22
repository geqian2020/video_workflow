# video_workflow

本地中文课件讲解工作台：上传 PPTX/PDF，编辑逐页讲稿，换一个卡通讲师，试听后导出 MP4 和字幕。

基于 [SlideStream 2.19.0](https://github.com/michael-borck/slide-stream) 的解析和服务接口开发。当前版本提供中文语音、独立角色布局、逐页编辑、项目保存及视频候选页面提取工具。

## 当前功能

- 上传 PPTX/PDF，保留静态页面、空白页和原始页码。
- 从备注或页面文字起步，逐页编辑、保存和试听讲稿。
- 上传卡通角色，点击标记嘴部，生成音量驱动的嘴型和轻微摆动。
- 分别导出单页预览、完整 MP4、中文 SRT 和时间线 JSON。
- 持久保存项目；修改内容后标记旧视频；按讲稿内容缓存语音。
- 可选接入 Presenton，从文案生成同一份文稿的可编辑 PPTX 和 PDF。
- 可选连接兼容的模型服务，起草逐页讲稿。
- 从本地视频的课件区域提取候选截图和来源时间，供人工复原课件。

## 安装与启动

需要 Python 3.10+，建议 3.11 或 3.12。Windows PowerShell：

```powershell
git clone https://github.com/geqian2020/video_workflow.git
cd video_workflow
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m video_workflow
```

打开 [本地工作台](http://127.0.0.1:8765)。不需要激活虚拟环境或修改 Windows 脚本执行策略。项目保存在 `data/`，可用 `--data` 指定其他目录。服务只绑定本机，按单进程运行。

macOS/Linux 使用 `.venv/bin/python -m video_workflow`，配音请选择在线模式，PPTX 转换需安装 LibreOffice。

### 课件与角色

PPTX 静态导图优先调用 Windows PowerPoint，其他环境调用 LibreOffice。没有转换工具时，请先把 PPT 导出 PDF 后上传。程序不会用文本重排冒充保留原版式。

上传透明 PNG 后，点击角色嘴巴中心，调整嘴部宽高，保存后先预览一页。首版是音量嘴型，不是精确音素口型；没有任意单张图的自然手势、走动或指向功能。

Windows 离线配音需要简体中文系统语音包。在线模式使用 edge-tts，相关讲稿会发送到语音服务；离线失败不会自动切到在线。

字幕按实际生成的语句音频计时，长句在画面上分页，分页时间按文字长度分配，未做逐字强制对齐。SRT 保留完整讲稿。

### 自动生成 PPT 与讲稿

复制 `.env.example` 为 `.env`，按需设置 `PRESENTON_URL`、`PRESENTON_API_KEY`，或 `WORKFLOW_LLM_URL`、`WORKFLOW_LLM_MODEL`、`WORKFLOW_LLM_API_KEY`。两种服务可以独立启用。

先在 [Presenton](https://github.com/presenton/presenton) 中配置其生成模型。生成服务调用一次，再导出同一文稿的 PDF，保持 PPTX 与视频画面一致。未配置时，界面明确禁用生成入口。

适配器已有模拟接口测试；开发环境未配置真实模型，暂未完成生成服务的实际联调。

### 从视频整理课件

请使用本地原视频/录屏文件：

```powershell
.\.venv\Scripts\python.exe -m video_workflow.extract reference.mp4 extracted --crop 0,0,0.75,0.85
```

`--crop` 是 x、y、宽、高四个比例，按实际课件区域调整，尽量排除人物和字幕。产物是候选截图与 `manifest.json` 时间索引。需要人工合并重复页、核对文字和图表，再制作可编辑课件或截图版课件。工具不自动补全被遮挡的内容。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
node --check src/video_workflow/static/app.js
.\.venv\Scripts\python.exe examples/smoke_render.py --character path/to/character.png
```

自测使用明确标注的测试页，验证实际中文语音、嘴型、字幕和编码。它不是参考视频的复刻结果。

当前上限：60 页，单次视频 60 分钟。不保留 PPT 原有动画和内嵌视频。中断任务标为失败，素材和语音缓存保留；尚未自动续跑中断的视频合成步骤。

开发状态见 [docs/STATUS.md](docs/STATUS.md)，依赖来源见 [THIRD_PARTY.md](THIRD_PARTY.md)。
