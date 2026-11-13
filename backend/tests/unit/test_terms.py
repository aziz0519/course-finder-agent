"""Term parsing and calendar-aware ordering."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.terms import Term, coerce_season


def test_parse_produces_a_label_round_trip() -> None:
    term = Term.parse("Fall 2026")

    assert term.season == "Fall"
    assert term.year == 2026
    assert term.label == "Fall 2026"
    assert str(term) == "Fall 2026"


def test_seasons_order_within_a_year() -> None:
    assert Term.parse("Spring 2026") < Term.parse("Summer 2026")
    assert Term.parse("Summer 2026") < Term.parse("Fall 2026")
    assert Term.parse("Spring 2026") < Term.parse("Fall 2026")


def test_ordering_across_years_starting_in_fall() -> None:
    # Lexicographic string comparison puts Spring after Fall in the same year.
    assert "Spring 2026" > "Fall 2026"
    # Calendar order, which is also academic order, puts Spring first.
    assert Term.parse("Spring 2026") < Term.parse("Fall 2026")
    assert Term.parse("Fall 2025") < Term.parse("Spring 2026")
    assert Term.parse("Summer 2026") < Term.parse("Fall 2026")


def test_equality_and_hashability() -> None:
    assert Term.parse("Spring 2027") == Term.parse("Spring 2027")
    assert len({Term.parse("Spring 2027"), Term.parse("Spring 2027")}) == 1


def test_unrecognised_season_is_rejected() -> None:
    with pytest.raises(ValueError, match="unrecognised term label"):
        Term.parse("Autumn 2026")


def test_missing_year_is_rejected() -> None:
    with pytest.raises(ValueError):
        Term.parse("Fall")


def test_year_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        Term(season="Fall", year=1800)


def test_coerce_season_accepts_a_year_qualified_offering() -> None:
    assert coerce_season("Fall 2026") == "Fall"
    assert coerce_season("Spring") == "Spring"


def test_coerce_season_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="unrecognised offering season"):
        coerce_season("Michaelmas")
