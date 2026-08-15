"""Monotonic deterministic priority-queue execution kernel."""

from __future__ import annotations

import heapq
from collections.abc import Callable

from nr_ran_sim.errors import InvariantViolation, RunExecutionError
from nr_ran_sim.kernel.events import (
    EventKind,
    EventOrderKey,
    EventResult,
    ScheduledEvent,
    SemanticEvent,
)
from nr_ran_sim.kernel.trace import SemanticTrace

EventHandler = Callable[[ScheduledEvent], EventResult]


class DeterministicKernel:
    """Process events in the exact ADR-0001 order and reject temporal regressions."""

    def __init__(self) -> None:
        self._heap: list[tuple[EventOrderKey, ScheduledEvent]] = []
        self._pending_keys: set[EventOrderKey] = set()
        self._known_event_ids: set[str] = set()
        self._handlers: dict[EventKind, EventHandler] = {}
        self._trace: list[SemanticEvent] = []
        self._last_key: EventOrderKey | None = None
        self.current_tick = 0

    def register_handler(self, kind: EventKind, handler: EventHandler) -> None:
        if kind in self._handlers:
            raise InvariantViolation(
                "event kind already has a registered handler",
                {"kind": kind.value, "requirement": "SYS-009"},
            )
        self._handlers[kind] = handler

    def schedule(self, event: ScheduledEvent) -> None:
        if event.tick < self.current_tick:
            raise InvariantViolation(
                "cannot schedule an event earlier than the current simulation tick",
                {
                    "event_id": str(event.id),
                    "event_tick": event.tick,
                    "current_tick": self.current_tick,
                    "requirement": "TIME-009",
                },
            )
        if self._last_key is not None and event.order_key <= self._last_key:
            raise InvariantViolation(
                "new event would regress or duplicate the processed event order",
                {
                    "event_id": str(event.id),
                    "order_key": event.order_key,
                    "last_order_key": self._last_key,
                    "requirement": "TIME-004",
                },
            )
        event_id = str(event.id)
        if event_id in self._known_event_ids or event.order_key in self._pending_keys:
            raise InvariantViolation(
                "event identity or complete ordering key is duplicated",
                {
                    "event_id": event_id,
                    "order_key": event.order_key,
                    "requirement": "SYS-007",
                },
            )
        self._known_event_ids.add(event_id)
        self._pending_keys.add(event.order_key)
        heapq.heappush(self._heap, (event.order_key, event))

    def run(self, until_tick: int) -> SemanticTrace:
        if until_tick < self.current_tick:
            raise InvariantViolation(
                "kernel stop tick is earlier than current time",
                {
                    "until_tick": until_tick,
                    "current_tick": self.current_tick,
                    "requirement": "TIME-009",
                },
            )
        while self._heap and self._heap[0][0][0] <= until_tick:
            order_key, event = heapq.heappop(self._heap)
            self._pending_keys.remove(order_key)
            if self._last_key is not None and order_key <= self._last_key:
                raise InvariantViolation(
                    "event queue produced non-monotonic output",
                    {
                        "event_id": str(event.id),
                        "order_key": order_key,
                        "last_order_key": self._last_key,
                        "requirement": "TIME-009",
                    },
                )
            handler = self._handlers.get(event.kind)
            if handler is None:
                raise RunExecutionError(
                    "scheduled event has no registered handler",
                    {"event_id": str(event.id), "kind": event.kind.value},
                )
            self.current_tick = event.tick
            self._last_key = order_key
            result = handler(event)
            self._trace.append(SemanticEvent.from_result(event, result))
            for followup in result.followups:
                self.schedule(followup)
        self.current_tick = until_tick
        return SemanticTrace(tuple(self._trace))

    @property
    def pending_event_count(self) -> int:
        return len(self._heap)
