from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

import boto3
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.outbox import Outbox


class OutboxPublisher:
    def __init__(self, interval_sec: float = 1.0):
        self.interval_sec = interval_sec
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._sqs = None
        if settings.AWS_REGION and settings.AWS_SQS_QUEUE_URL:
            self._sqs = boto3.client("sqs", region_name=settings.AWS_REGION)

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
        if not self._sqs or not settings.AWS_SQS_QUEUE_URL:
            return
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
                payload = json.loads(row.payload)
                # Provide FIFO grouping if available
                message_group_id = str(payload.get("drone_id", payload.get("aggregate_id", "default")))
                dedup_id = f"outbox-{row.id}"
                try:
                    self._sqs.send_message(
                        QueueUrl=settings.AWS_SQS_QUEUE_URL,
                        MessageBody=json.dumps(payload),
                        MessageGroupId=message_group_id,
                        MessageDeduplicationId=dedup_id,
                    )
                    row.status = "published"
                    from sqlalchemy.sql import func
                    row.published_at = func.now()
                    db.add(row)
                    db.commit()
                except Exception as pub_ex:
                    row.status = "failed"
                    row.last_error = str(pub_ex)
                    db.add(row)
                    db.commit()
        finally:
            db.close()

# Singleton instance used by app.main
publisher = OutboxPublisher(interval_sec=1.0)
