"""Term value object.

Term order is ``(year, season)``, never lexicographic: ``"Spring 2026"`` must sort
before ``"Fall 2026"``. All eligibility decisions rely on this ordering.
"""

from __future__ import annotations

import re
from functools import total_ordering
from typing import Annotated, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

Season = Literal["Winter", "Spring", "Summer", "Fall"]

SEASONS: Final[tuple[Season, ...]] = ("Winter", "Spring", "Summer", "Fall")
SEASON_ORDER: Final[dict[str, int]] = {season: index for index, season in enumerate(SEASONS)}

_TERM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(Winter|Spring|Summer|Fall) (\d{4})$")


@total_ordering
class Term(BaseModel):
    """An academic term such as ``Fall 2026`` with calendar-aware ordering."""

    model_config = ConfigDict(frozen=True)

    season: Season
    year: int = Field(ge=1900, le=2200)

    @classmethod
    def parse(cls, label: str) -> Term:
        """Parse ``"Fall 2026"``. Raises ``ValueError`` on any other shape."""
        match = _TERM_PATTERN.match(label.strip())
        if match is None:
            raise ValueError(
                f"unrecognised term label {label!r}; expected '<Season> <YYYY>' "
                f"with season in {', '.join(SEASONS)}"
            )
        return cls(season=match.group(1), year=int(match.group(2)))  # type: ignore[arg-type]

    @property
    def label(self) -> str:
        return f"{self.season} {self.year}"

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.year, SEASON_ORDER[self.season])

    def __str__(self) -> str:
        return self.label

    def __repr__(self) -> str:
        return f"Term({self.label!r})"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Term):
            return NotImplemented
        return self.sort_key < other.sort_key


def coerce_term(value: object) -> Term:
    """Accept a ``Term``, a ``{"season", "year"}`` mapping, or a term label."""
    if isinstance(value, Term):
        return value
    if isinstance(value, str):
        return Term.parse(value)
    if isinstance(value, dict):
        return Term.model_validate(value)
    raise ValueError(f"cannot interpret {value!r} as a term")


TermField = Annotated[Term, BeforeValidator(coerce_term)]


def coerce_season(value: object) -> Season:
    """Normalise an offering such as ``"Fall 2026"`` to its season."""
    if not isinstance(value, str):
        raise ValueError(f"cannot interpret {value!r} as an offering season")
    season = value.strip().split(" ", 1)[0]
    if season not in SEASON_ORDER:
        raise ValueError(
            f"unrecognised offering season {value!r}; expected one of {', '.join(SEASONS)}"
        )
    return season  # type: ignore[return-value]


SeasonField = Annotated[Season, BeforeValidator(coerce_season)]
