from __future__ import annotations

import json
import threading
import time
from queue import Queue, Empty
from typing import Any, Dict, List

from app.core.database import Base, engine

# Ensure tables exist for local demo
Base.metadata.create_all(bind=engine)

# Import the same handler used by the Lambda worker to keep behavior identical
try:
    from aws.functions import command_worker  # type: ignore
except Exception as ex:  # pragma: no cover
    command_worker = None  # type: ignore


class LocalQueueBus:
    def __init__(self) -> None:
        self._queue: Queue[dict[str, Any]] = Queue()
        self._stop = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2)

    def send(self, message: dict[str, Any], message_group_id: str | None = None, dedup_id: str | None = None) -> None:
        # For local bus, we ignore group and dedup but preserve payload
        self._queue.put(message)

    def _run(self) -> None:
        while not self._stop:
            try:
                batch: List[dict[str, Any]] = []
                # Drain up to 10 messages to simulate SQS batch
                for _ in range(10):
                    try:
                        msg = self._queue.get_nowait()
                        batch.append(msg)
                    except Empty:
                        break
                if not batch:
                    time.sleep(0.2)
                    continue
                if command_worker is not None:
                    event = {"Records": [{"body": json.dumps(m)} for m in batch]}
                    # Call the same handler used in Lambda worker
                    print(f"[LocalQueueBus] Processing {len(batch)} messages")  # Debug
                    try:
                        result = command_worker.handler(event, None)
                        print(f"[LocalQueueBus] Result: {result}")  # Debug
                    except Exception as e:
                        print(f"[LocalQueueBus] Worker error: {e}")  # Debug
                        import traceback
                        traceback.print_exc()
                else:
                    # Fallback: no-op if import failed
                    print(f"[LocalQueueBus] command_worker is None")  # Debug
            except Exception as ex:  # pragma: no cover
                # Log and continue; we don't want the local bus to crash the app
                print(f"[LocalQueueBus] error: {ex}")
                import traceback
                traceback.print_exc()


# Singleton instance
local_bus = LocalQueueBus()
