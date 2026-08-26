import re
from datetime import timedelta
from typing import Any

from app.utils.datetime_utils import parse_relative_datetime, now_utc

_PERSON_RE = re.compile(r"\b(?:with|for|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")
_TITLE_WORDS = ["meeting", "call", "appointment", "sync", "interview",
                "review", "catch up", "standup", "session"]
_STOP = {"me", "my", "i", "the", "a", "an", "at", "on", "in", "tomorrow",
         "today", "tonight", "next", "please"}


class EntityExtractor:
    """Rule-first hybrid (PRD §8). Deterministic where rules are reliable,
    leaving the ML classifier responsible for intent only."""

    def extract(self, text: str, intent: str) -> dict[str, Any]:
        ent: dict[str, Any] = {}

        when = parse_relative_datetime(text)
        if when:
            ent["datetime"] = when.isoformat()
            ent["end_datetime"] = (when + timedelta(hours=1)).isoformat()

        m = _PERSON_RE.search(text)
        if m and m.group(1).lower() not in _STOP:
            ent["person"] = m.group(1)

        lowered = text.lower()
        for w in _TITLE_WORDS:
            if w in lowered:
                ent["event_type"] = w
                break

        if intent == "SCHEDULE_EVENT":
            etype = ent.get("event_type", "Meeting").title()
            ent["title"] = f"{etype} with {ent['person']}" if ent.get("person") else etype

        if intent == "CREATE_REMINDER":
            ent["task"] = self._reminder_task(text)

        return ent

    @staticmethod
    def _reminder_task(text: str) -> str:
        t = re.sub(r"^\s*(please\s+)?(remind me( to| about)?|set (a )?reminder( to)?|ping me to)\s*",
                   "", text, flags=re.I)
        t = re.split(r"\b(?:at|on|tomorrow|today|tonight|next|in \d+ day)\b", t, flags=re.I)[0]
        return t.strip(" ,.") or "Reminder"


entity_extractor = EntityExtractor()
