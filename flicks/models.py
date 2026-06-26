from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    """A single film screening at one theater."""

    title: str
    start: datetime  # timezone-aware, in the theater's local zone
    theater: str
    url: str
    poster: str | None = None
    imdb: str | None = None  # canonical https://www.imdb.com/title/tt…/ when known

    @property
    def date_key(self) -> str:
        return self.start.strftime("%Y-%m-%d")

    @property
    def time_label(self) -> str:
        # e.g. "7:00pm"; strip a leading zero from the hour
        return self.start.strftime("%I:%M%p").lstrip("0").lower()
