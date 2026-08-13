"""Kênh đẩy sự kiện tiến độ task qua Redis Pub/Sub.

Vì sao cần: endpoint WebSocket `/ws/task/{id}` trước đây tự **polling** Celery result
backend mỗi giây. Nhìn từ trình duyệt thì đúng là real-time (server chỉ gửi khi có thay
đổi), nhưng nhìn từ server thì vẫn là vòng lặp hỏi Redis liên tục cho **mỗi** kết nối:
100 người xem cùng lúc là 100 vòng lặp, mỗi giây 100 lần hỏi Redis, phần lớn trả về đúng
cái đã biết. Độ trễ cũng bị chặn dưới bởi chu kỳ polling.

Ở đây Worker **tự phát** sự kiện lên một channel khi trạng thái đổi, endpoint WebSocket
lắng nghe channel đó. Không có Redis thì `subscribe()` trả None và phía gọi tự quay về
đường polling cũ — mất tối ưu chứ không mất tính năng, đúng nguyên tắc graceful fallback.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "mep_task_events:"


def channel_for(task_id: str) -> str:
    return f"{CHANNEL_PREFIX}{task_id}"


def _client():
    try:
        import redis
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        password = os.environ.get("REDIS_PASSWORD", "") or None
        client = redis.Redis(host=host, port=port, db=0, password=password,
                             socket_connect_timeout=1)
        client.ping()
        return client
    except Exception as e:
        logger.debug("Redis không khả dụng cho kênh sự kiện task: %s", e)
        return None


def publish(task_id: str, payload: dict) -> bool:
    """Phát một sự kiện tiến độ. Trả True nếu đã đẩy được lên Redis.

    Không đẩy được **không phải là lỗi**: client vẫn nhận đúng trạng thái qua đường
    polling dự phòng, chỉ chậm hơn. Nên chỗ này không bao giờ được ném exception ra
    ngoài — nó nằm trong đường chạy của task nghiệp vụ.
    """
    client = _client()
    if client is None:
        return False
    try:
        client.publish(channel_for(task_id), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as e:
        logger.debug("Không phát được sự kiện task %s: %s", task_id, e)
        return False


def subscribe(task_id: str):
    """Trả về đối tượng pubsub đã đăng ký channel, hoặc None nếu không có Redis.

    Người gọi phải tự đóng (`pubsub.close()`), thường trong `finally`.
    """
    client = _client()
    if client is None:
        return None
    try:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel_for(task_id))
        return pubsub
    except Exception as e:
        logger.debug("Không đăng ký được kênh sự kiện task %s: %s", task_id, e)
        return None


def get_message(pubsub, timeout: float = 1.0) -> dict | None:
    """Lấy một sự kiện, hoặc None nếu hết thời gian chờ. Không ném exception."""
    try:
        raw = pubsub.get_message(timeout=timeout)
    except Exception as e:
        logger.debug("Lỗi khi đọc kênh sự kiện: %s", e)
        return None
    if not raw or raw.get("type") != "message":
        return None
    data = raw.get("data")
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    try:
        return json.loads(data)
    except Exception:
        return None
