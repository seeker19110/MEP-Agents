"""Kênh đẩy sự kiện tiến độ (`src/task_events.py`) và WebSocket dùng nó.

Trước đây `/ws/task/{id}` tự polling Celery result backend mỗi giây cho MỖI kết nối: 100
người xem cùng lúc là 100 vòng lặp hỏi Redis mỗi giây, phần lớn để nhận lại đúng cái đã
biết. Nay Worker tự phát sự kiện, endpoint chỉ ngồi nghe.

Bộ test này canh hai điều quan trọng như nhau: đường Pub/Sub chạy đúng, VÀ đường polling
dự phòng vẫn nguyên vẹn khi không có Redis (môi trường dev, Redis tạm gián đoạn).
"""
import asyncio
import json
import types

import pytest

from src import api, task_events


class _FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


class _MutableAsyncResult:
    def __init__(self, state="PENDING"):
        self.state = state
        self.info = None
        self.result = None


class _FakePubSub:
    """Trả lần lượt các sự kiện đã dựng sẵn, rồi None (hết thời gian chờ)."""

    def __init__(self, events):
        self._events = list(events)
        self.closed = False

    def get_message(self, timeout=1.0):
        if not self._events:
            return None
        return {"type": "message", "data": json.dumps(self._events.pop(0))}

    def close(self):
        self.closed = True


# --- Tầng kênh sự kiện ---

def test_publish_returns_false_without_redis(monkeypatch):
    """Không có Redis thì bỏ qua trong im lặng — task nghiệp vụ không được hỏng theo."""
    monkeypatch.setattr(task_events, "_client", lambda: None)
    assert task_events.publish("t1", {"status": "Processing"}) is False


def test_subscribe_returns_none_without_redis(monkeypatch):
    monkeypatch.setattr(task_events, "_client", lambda: None)
    assert task_events.subscribe("t1") is None


def test_publish_sends_to_task_channel(monkeypatch):
    sent = {}

    class _FakeRedis:
        def publish(self, channel, data):
            sent["channel"] = channel
            sent["data"] = data

    monkeypatch.setattr(task_events, "_client", lambda: _FakeRedis())
    assert task_events.publish("t1", {"status": "success"}) is True
    assert sent["channel"] == task_events.channel_for("t1")
    assert json.loads(sent["data"])["status"] == "success"


def test_publish_survives_broken_redis(monkeypatch):
    class _BrokenRedis:
        def publish(self, channel, data):
            raise RuntimeError("mất kết nối")

    monkeypatch.setattr(task_events, "_client", lambda: _BrokenRedis())
    assert task_events.publish("t1", {"status": "success"}) is False


def test_get_message_ignores_non_message_frames():
    pubsub = types.SimpleNamespace(
        get_message=lambda timeout=1.0: {"type": "subscribe", "data": 1})
    assert task_events.get_message(pubsub) is None


# --- WebSocket dùng kênh sự kiện ---

def test_websocket_uses_events_instead_of_polling(monkeypatch):
    """Có Redis thì KHÔNG được gọi tới vòng ngủ polling lần nào."""
    fake_result = _MutableAsyncResult()
    pubsub = _FakePubSub([
        {"status": "Processing", "logs": ["Đang đọc bản vẽ"]},
        {"status": "success", "logs": ["Xong"], "result": {"excel_path": "boq.xlsx"}},
    ])
    polled = {"n": 0}

    async def _should_not_poll(_seconds):
        polled["n"] += 1

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: fake_result)
    monkeypatch.setattr(api, "_WS_POLL_SLEEP", _should_not_poll)
    monkeypatch.setattr("src.task_events.subscribe", lambda task_id: pubsub)

    ws = _FakeWebSocket()
    asyncio.run(api.ws_task_status(ws, "some-id"))

    assert polled["n"] == 0, "vẫn còn polling dù đã có kênh sự kiện"
    # Ba khung: ảnh chụp trạng thái lúc mở kết nối, rồi hai sự kiện. Khung đầu và sự kiện
    # đầu cùng mang status "Processing" nhưng KHÁC nội dung log, nên cả hai đều được gửi —
    # lọc trùng so sánh cả payload chứ không chỉ status.
    assert [m["status"] for m in ws.sent] == ["Processing", "Processing", "success"]
    assert ws.sent[1]["logs"] == ["Đang đọc bản vẽ"]
    assert ws.sent[-1]["result"] == {"excel_path": "boq.xlsx"}
    assert pubsub.closed, "kênh phải được đóng, nếu không sẽ rò kết nối Redis"


def test_websocket_sends_current_state_immediately(monkeypatch):
    """Client mở kết nối MUỘN (task đã xong) phải nhận kết quả ngay, không treo chờ sự
    kiện sẽ không bao giờ tới nữa."""
    done = _MutableAsyncResult(state="SUCCESS")
    done.result = {"excel_path": "boq.xlsx"}

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: done)
    monkeypatch.setattr("src.task_events.subscribe", lambda task_id: _FakePubSub([]))

    ws = _FakeWebSocket()
    asyncio.run(api.ws_task_status(ws, "some-id"))

    assert len(ws.sent) == 1
    assert ws.sent[0]["status"] == "success"


def test_websocket_falls_back_to_polling_without_redis(monkeypatch):
    """Không có Redis thì hành vi cũ phải còn nguyên — mất tối ưu, không mất tính năng."""
    fake_result = _MutableAsyncResult()
    states = iter([
        ("PROGRESS", {"logs": ["Đang xử lý..."]}, None),
        ("SUCCESS", None, {"excel_path": "boq.xlsx"}),
    ])
    polled = {"n": 0}

    async def _fake_sleep(_seconds):
        polled["n"] += 1
        state, info, result = next(
            states, (fake_result.state, fake_result.info, fake_result.result))
        fake_result.state, fake_result.info, fake_result.result = state, info, result

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: fake_result)
    monkeypatch.setattr(api, "_WS_POLL_SLEEP", _fake_sleep)
    monkeypatch.setattr("src.task_events.subscribe", lambda task_id: None)

    ws = _FakeWebSocket()
    asyncio.run(api.ws_task_status(ws, "some-id"))

    assert polled["n"] > 0, "không có Redis thì phải quay về polling"
    assert [m["status"] for m in ws.sent] == ["Processing", "Processing", "success"]


def test_websocket_recovers_when_no_event_arrives(monkeypatch):
    """Worker chết giữa chừng không kịp phát sự kiện: hết thời gian chờ thì phải tự tra
    lại trạng thái, không ngồi đợi vô hạn."""
    fake_result = _MutableAsyncResult()
    calls = {"n": 0}

    def _timeout_then_finish(pubsub, timeout):
        calls["n"] += 1
        fake_result.state = "SUCCESS"
        fake_result.result = {"excel_path": "boq.xlsx"}
        return None  # hết thời gian chờ, không có sự kiện nào

    monkeypatch.setattr(api, "AsyncResult", lambda task_id, app: fake_result)
    monkeypatch.setattr("src.task_events.subscribe", lambda task_id: _FakePubSub([]))
    monkeypatch.setattr("src.task_events.get_message", _timeout_then_finish)

    ws = _FakeWebSocket()
    asyncio.run(api.ws_task_status(ws, "some-id"))

    assert calls["n"] >= 1
    assert ws.sent[-1]["status"] == "success"


# --- Worker phát sự kiện ---

def test_worker_publishes_success_event(monkeypatch):
    from src import celery_app as ca

    published = []
    monkeypatch.setattr("src.task_events.publish",
                        lambda task_id, payload: published.append((task_id, payload)))
    task = types.SimpleNamespace(request=types.SimpleNamespace(id="t-42"))
    ca._publish_event(task, {"status": "success"})

    assert published == [("t-42", {"status": "success"})]


def test_worker_event_without_task_id_is_ignored(monkeypatch):
    """Chạy `.run()` trực tiếp trong test thì không có request/id thật — phải bỏ qua."""
    from src import celery_app as ca

    published = []
    monkeypatch.setattr("src.task_events.publish",
                        lambda task_id, payload: published.append(task_id))
    ca._publish_event(types.SimpleNamespace(request=None), {"status": "success"})
    assert published == []
