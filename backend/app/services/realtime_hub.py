"""
Mission-Scoped Real-Time Event Pub/Sub Hub for SSE Streaming.
Strictly isolates subscribers per mission_id and provides thread-safe publishing
so synchronous or asynchronous handlers deliver events cleanly without cross-mission leaks.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
import uuid
from typing import Any, Dict, List, Set


@dataclass(eq=False)
class _Subscriber:
    subscriber_id: str
    mission_id: str
    astronaut_id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


class MissionRealtimeHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, Set[_Subscriber]] = defaultdict(set)

    def subscribe(self, mission_id: str, astronaut_id: str) -> _Subscriber:
        loop = asyncio.get_running_loop()
        sub = _Subscriber(
            subscriber_id=str(uuid.uuid4()),
            mission_id=mission_id,
            astronaut_id=astronaut_id,
            loop=loop,
            queue=asyncio.Queue(maxsize=256),
        )
        with self._lock:
            self._subscribers[mission_id].add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            bucket = self._subscribers.get(sub.mission_id)
            if bucket is not None:
                bucket.discard(sub)
                if not bucket:
                    self._subscribers.pop(sub.mission_id, None)

    def active_subscriber_count(self, mission_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(mission_id, set()))

    def active_astronaut_ids(self, mission_id: str) -> List[str]:
        with self._lock:
            return sorted({s.astronaut_id for s in self._subscribers.get(mission_id, set())})

    def publish_mission_event(
        self,
        mission_id: str,
        *,
        event_type: str,
        payload: Dict[str, Any],
        event_seq: int | None = None,
    ) -> int:
        message = {
            "event_type": event_type,
            "mission_id": mission_id,
            "event_seq": event_seq,
            "published_at_utc": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with self._lock:
            targets = list(self._subscribers.get(mission_id, set()))

        delivered = 0
        for sub in targets:
            try:
                if sub.loop.is_closed():
                    continue
                sub.loop.call_soon_threadsafe(self._enqueue_drop_oldest, sub.queue, message)
                delivered += 1
            except RuntimeError:
                continue
        return delivered

    @staticmethod
    def _enqueue_drop_oldest(queue: asyncio.Queue, message: Dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def format_sse(event_name: str, data: Dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
