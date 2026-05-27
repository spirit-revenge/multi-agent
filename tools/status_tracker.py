"""
In-memory status tracker for SSE progress reporting.
Each crew execution gets a task_id; the frontend subscribes to receive
real-time status updates via Server-Sent Events.
"""

import queue
import uuid
from datetime import datetime


class CrewStatusTracker:
    def __init__(self):
        self._queues = {}

    def create_task(self) -> str:
        task_id = str(uuid.uuid4())[:8]
        self._queues[task_id] = queue.Queue()
        return task_id

    def update(self, task_id: str, step: str, detail: str):
        if task_id in self._queues:
            self._queues[task_id].put({
                "step": step,
                "detail": detail,
                "timestamp": datetime.now().isoformat(),
            })

    def get_updates(self, task_id: str):
        q = self._queues.get(task_id)
        if q is None:
            return
        while True:
            try:
                msg = q.get(timeout=8)
                yield msg
            except queue.Empty:
                yield {"step": "heartbeat", "detail": ""}

    def cleanup(self, task_id: str):
        self._queues.pop(task_id, None)


status_tracker = CrewStatusTracker()
