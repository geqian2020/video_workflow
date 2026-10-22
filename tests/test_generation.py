from video_workflow.generation import generate_deck
from video_workflow.models import Generation


def test_generate_once_and_export_same_presentation(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTON_URL", "http://localhost:5001")
    posts, downloads = [], []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"presentation_id": "deck123", "path": "/app_data/deck.pptx"}

    def post(url, **kwargs):
        posts.append((url, kwargs))
        return Response()

    def download(base, headers, data, path):
        downloads.append(path)
        path.write_bytes(b"fixture")

    exported = []
    monkeypatch.setattr("video_workflow.generation.requests.post", post)
    monkeypatch.setattr("video_workflow.generation.download_export", download)
    monkeypatch.setattr(
        "slide_stream.presenton.PresentonClient.export",
        lambda self, identifier, kind: (
            exported.append((identifier, kind)) or {"path": "/app_data/deck.pdf"}
        ),
    )
    pptx, pdf = generate_deck(
        Generation(content="这个主题具有足够长度，供生成测试使用。"), tmp_path
    )
    assert len(posts) == 1
    assert posts[0][1]["json"]["language"] == "Chinese"
    assert exported == [("deck123", "pdf")]
    assert downloads == [pptx, pdf]
