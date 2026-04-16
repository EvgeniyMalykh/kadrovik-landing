"""
Redis-relay email backend для Django.
Контейнер не имеет доступа к SMTP — пишем задачу в Redis.
Хост-процесс email_relay.py читает из Redis и отправляет через SMTP.
"""
import json
import redis
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings


class RedisRelayEmailBackend(BaseEmailBackend):
    """Email backend — пишет в Redis очередь, хост отправляет через SMTP."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._redis = None

    def open(self):
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    getattr(settings, "REDIS_RELAY_URL", "redis://redis:6379/2")
                )
                self._redis.ping()
            except Exception as e:
                if not self.fail_silently:
                    raise
                return False
        return True

    def close(self):
        self._redis = None

    def send_messages(self, email_messages):
        if not self.open():
            return 0
        sent = 0
        queue_key = getattr(settings, "EMAIL_RELAY_QUEUE_KEY", "email_relay_queue")
        for msg in email_messages:
            try:
                body_html = ""
                body_text = msg.body
                for alt_body, mime_type in getattr(msg, "alternatives", []):
                    if mime_type == "text/html":
                        body_html = alt_body
                        break
                task = {
                    "to": msg.to[0] if msg.to else "",
                    "subject": msg.subject,
                    "from": msg.from_email,
                    "html": body_html,
                    "text": body_text,
                }
                self._redis.rpush(queue_key, json.dumps(task, ensure_ascii=False))
                sent += 1
            except Exception as e:
                if not self.fail_silently:
                    raise
        return sent
