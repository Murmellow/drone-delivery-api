from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

import boto3  # type: ignore
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.outbox import Outbox


class OutboxPublisher:
    _thread: threading.Thread | None
    _sqs: Any | None
    _local: Any | None
    def __init__(self, interval_sec: float = 1.0):
        self.interval_sec = interval_sec
        self._stop = False
        self._thread = None
        self._sqs = None
        self._local = None
        if settings.AWS_REGION and settings.AWS_SQS_QUEUE_URL:
            self._sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
        else:
            # Fallback to in-process local bus for demos without AWS creds
            try:
                from app.services.local_bus import local_bus
                self._local = local_bus
            except Exception:
                self._local = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop:
            try:
                self._publish_pending()
            except Exception as ex:
                # Best-effort logging; avoid crashing background thread
                print(f"[OutboxPublisher] Error: {ex}")
            time.sleep(self.interval_sec)

    def _publish_pending(self) -> None:
        db: Session = SessionLocal()
        try:
            rows = (
                db.query(Outbox)
                .filter(Outbox.status == "pending")
                .order_by(Outbox.created_at.asc())
                .limit(10)
                .all()
            )
            for row in rows:
                payload_json = str(getattr(row, "payload"))
                payload = json.loads(payload_json)
                # Provide FIFO grouping if available
                message_group_id = str(payload.get("drone_id", payload.get("aggregate_id", "default")))
                dedup_id = f"outbox-{getattr(row, 'id')}"
                try:
                    if self._sqs and settings.AWS_SQS_QUEUE_URL:
                        self._sqs.send_message(
                            QueueUrl=settings.AWS_SQS_QUEUE_URL,
                            MessageBody=json.dumps(payload),
                            MessageGroupId=message_group_id,
                            MessageDeduplicationId=dedup_id,
                        )
                    elif self._local:
                        self._local.send(payload, message_group_id, dedup_id)
                    else:
                        # No publisher configured
                        continue
                    setattr(row, "status", "published")
                    setattr(row, "published_at", datetime.now(timezone.utc))
                    db.add(row)
                    db.commit()
                except Exception as pub_ex:
                    setattr(row, "status", "failed")
                    setattr(row, "last_error", str(pub_ex))
                    db.add(row)
                    db.commit()
        finally:
            db.close()

# Singleton instance used by app.main
publisher = OutboxPublisher(interval_sec=1.0)
