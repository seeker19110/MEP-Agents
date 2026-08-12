"""AI Computer Vision (YOLO) nhận diện thiết bị trên bản vẽ (src/vision_tools.py).

Không tải model YOLO thật (nặng, cần mạng) — model được giả lập (fake) để kiểm tra
luồng xử lý: đường dẫn an toàn, file không tồn tại, model không khả dụng, và định dạng
báo cáo kết quả nhận diện.
"""
import os

import pytest

import src.vision_tools as vision_tools
from src.vision_tools import detect_cad_symbols_yolo
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    vision_tools._YOLO_MODEL = None
    yield tmp_path
    vision_tools._YOLO_MODEL = None


class _FakeBox:
    def __init__(self, cls_id, conf):
        self.cls = [cls_id]
        self.conf = [conf]


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeModel:
    names = {0: "diffuser", 1: "sprinkler"}

    def __init__(self, boxes):
        self._boxes = boxes

    def predict(self, source, save=False):
        return [_FakeResult(self._boxes)]


def test_returns_message_when_model_unavailable(workspace, monkeypatch):
    monkeypatch.setattr(vision_tools, "get_yolo_model", lambda: None)
    result = detect_cad_symbols_yolo.invoke({"image_path": "anything.png"})
    assert "not available" in result


def test_returns_message_when_file_missing(workspace, monkeypatch):
    monkeypatch.setattr(vision_tools, "get_yolo_model", lambda: _FakeModel([]))
    result = detect_cad_symbols_yolo.invoke({"image_path": "missing.png"})
    assert "không tồn tại" in result


def test_reports_no_detection_when_no_boxes(workspace, monkeypatch):
    img_path = os.path.join(str(workspace), "drawing.png")
    with open(img_path, "wb") as f:
        f.write(b"fake image bytes")

    monkeypatch.setattr(vision_tools, "get_yolo_model", lambda: _FakeModel([]))
    result = detect_cad_symbols_yolo.invoke({"image_path": "drawing.png"})
    assert "Không tìm thấy thiết bị" in result


def test_reports_detected_items_with_confidence(workspace, monkeypatch):
    img_path = os.path.join(str(workspace), "drawing.png")
    with open(img_path, "wb") as f:
        f.write(b"fake image bytes")

    boxes = [_FakeBox(0, 0.91), _FakeBox(1, 0.77)]
    monkeypatch.setattr(vision_tools, "get_yolo_model", lambda: _FakeModel(boxes))
    result = detect_cad_symbols_yolo.invoke({"image_path": "drawing.png"})
    assert "diffuser (0.91)" in result
    assert "sprinkler (0.77)" in result


def test_predict_exception_is_reported_gracefully(workspace, monkeypatch):
    img_path = os.path.join(str(workspace), "drawing.png")
    with open(img_path, "wb") as f:
        f.write(b"fake image bytes")

    class _BoomModel:
        def predict(self, source, save=False):
            raise RuntimeError("boom")

    monkeypatch.setattr(vision_tools, "get_yolo_model", lambda: _BoomModel())
    result = detect_cad_symbols_yolo.invoke({"image_path": "drawing.png"})
    assert "Lỗi AI Vision" in result


def test_get_yolo_model_returns_none_when_ultralytics_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ultralytics":
            raise ImportError("no ultralytics")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    vision_tools._YOLO_MODEL = None
    assert vision_tools.get_yolo_model() is None
