"""Test doubles for Inngest and other external services."""

from dataclasses import dataclass, field

import inngest


@dataclass
class FakeInngestClient:
    """Records sent events for assertion without network calls."""

    sent_events: list[inngest.Event] = field(default_factory=list)

    async def send(
        self,
        events: inngest.Event | list[inngest.Event],
    ) -> None:
        """Async send — used by dispatch_task_ready (deprecated path)."""
        if isinstance(events, list):
            self.sent_events.extend(events)
        else:
            self.sent_events.append(events)

    def send_sync(
        self,
        events: inngest.Event | list[inngest.Event],
    ) -> None:
        """Sync send — used by cancel_task and plan_subtasks."""
        if isinstance(events, list):
            self.sent_events.extend(events)
        else:
            self.sent_events.append(events)

    def events_by_name(self, name: str) -> list[inngest.Event]:
        return [e for e in self.sent_events if e.name == name]

    def reset(self) -> None:
        self.sent_events.clear()
