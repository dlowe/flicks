"""Title normalization shared by rendering and filtering.

A film shown "in 70mm" or "presented by MUBI" is the same film as its plain
listing; such qualifiers should neither split it into its own row nor clutter
the title. Format qualifiers are stripped only when they trail the title, so
mid-title uses survive ("THEY LIVE and THE THING 35mm Double Feature" keeps its
name); presenter credits are stripped from either end.

`normalize()` composes both and is what callers should use.
"""

from __future__ import annotations

import re

# Film gauges (70mm/35mm/16mm) plus the projection/format labels that mark a
# presentation, not a different film.
_FORMAT_TOKEN = (
    r"(?:\d{2,3}mm|imax(?:\s+experience)?|xd|reald|3-?d|2-?d|"
    r"dolby(?:\s+cinema)?|d-?box|dcp|smc)"
)
# A trailing format qualifier: optional connector + token, optionally bracketed.
# "... in 70mm", "... (IMAX)", "... - 35mm", "... 70MM".
_TRAILING_FORMAT = re.compile(
    r"\s*[\(\[]?\s*(?:in|on|shot\s+on|presented\s+in|-)?\s*"
    + _FORMAT_TOKEN
    + r"\s*[\)\]]?\s*$",
    re.I,
)


def strip_format(title: str) -> str:
    """Drop a trailing film-format qualifier ('in 70mm', '(IMAX)') from a title."""
    stripped = _TRAILING_FORMAT.sub("", title).strip()
    return stripped or title


# Presenter credits: a prefix ("Oscilloscope Laboratories Presents – TITLE",
# "Mothlight NW Presents: TITLE") or a suffix ("TITLE // Presented by MUBI").
# The prefix requires "Presents" + a separator so plain titles ("A Christmas
# Present: ...") aren't eaten.
_PRESENTER_PREFIX = re.compile(r"^.{2,40}?\bpresents\b\s*[:–—-]\s+", re.I)
_PRESENTER_SUFFIX = re.compile(r"\s*(?://|[-–—·:])?\s*presented\s+by\b.*$", re.I)


def strip_presenter(title: str) -> str:
    """Drop a 'X Presents:' prefix or a 'presented by X' suffix from a title."""
    out = _PRESENTER_SUFFIX.sub("", title).strip()
    out = _PRESENTER_PREFIX.sub("", out).strip()
    return out or title


def normalize(title: str) -> str:
    """Strip presenter credits and trailing format qualifiers from a title."""
    return strip_format(strip_presenter(title))
