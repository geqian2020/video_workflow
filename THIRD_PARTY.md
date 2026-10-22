# 依赖来源

- [SlideStream](https://github.com/michael-borck/slide-stream)，固定版本 2.19.0，MIT。使用 PowerPoint 解析及 Presenton 客户端。
- [MoviePy](https://github.com/Zulko/moviepy)，视频/音频合成。
- [python-pptx](https://github.com/scanny/python-pptx)，课件读取和测试夹具。
- [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)，PDF 渲染与文字提取。
- [edge-tts](https://github.com/rany2/edge-tts)，可选在线中文语音。
- [Presenton](https://github.com/presenton/presenton)，Apache-2.0，可选独立服务，不随本项目打包。

其他依赖由 pyproject.toml 声明，各自的协议随其发行包提供。没有打包 THA4 或其他受限角色模型。

原创测试角色使用内置图像生成工具制作，提示词位于 examples/assets/otter-prompt.md。角色图像作为单独素材交付，不是运行程序所必需的默认资源。
