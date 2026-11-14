"""Provider-neutral grounded answer composition with an offline default."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import Field

from app.domain.models import DomainModel
from app.retrieval.readings import STOP_WORDS, Evidence


class ComposedClaim(DomainModel):
    text: str = Field(min_length=1, max_length=1000)
    evidence_index: int = Field(ge=0)


class ComposedAnswer(DomainModel):
    claims: tuple[ComposedClaim, ...] = Field(min_length=1, max_length=3)


class AnswerComposer(Protocol):
    """A configured adapter must stay within the supplied evidence.

    Network-backed implementations additionally need timeouts, retry/token/cost limits,
    and redacted logs. M3 ships only the deterministic offline implementation.
    """

    def compose(self, question: str, evidence: tuple[Evidence, ...]) -> ComposedAnswer: ...


class OfflineAnswerComposer:
    """Select the most question-relevant source sentences without adding model facts."""

    _sentence = re.compile(r"(?<=[.!?])\s+|\n+")

    def compose(self, question: str, evidence: tuple[Evidence, ...]) -> ComposedAnswer:
        if not evidence:
            raise ValueError("answer composition requires evidence")
        query_tokens = {
            token
            for token in re.findall(r"\w+", question.casefold(), re.UNICODE)
            if token not in STOP_WORDS and len(token) > 2
        }
        ranked: list[tuple[int, int, int, str]] = []
        for evidence_index, item in enumerate(evidence):
            sentences = [
                sentence.strip()
                for sentence in self._sentence.split(item.excerpt)
                if sentence.strip()
            ]
            for position, sentence in enumerate(sentences):
                sentence_tokens = set(re.findall(r"\w+", sentence.casefold(), re.UNICODE))
                score = len(query_tokens & sentence_tokens)
                ranked.append((-score, evidence_index, position, sentence[:1000]))
        ranked.sort()
        has_positive_match = bool(ranked and ranked[0][0] < 0)
        claims: list[ComposedClaim] = []
        seen: set[str] = set()
        for negative_score, evidence_index, _, sentence in ranked:
            if has_positive_match and negative_score == 0:
                continue
            normalized = " ".join(sentence.split()).casefold()
            if not normalized or normalized in seen:
                continue
            claims.append(
                ComposedClaim(
                    text=" ".join(sentence.split()),
                    evidence_index=evidence_index,
                )
            )
            seen.add(normalized)
            if len(claims) == 3:
                break
        if not claims:
            raise ValueError("approved evidence contains no composable text")
        return ComposedAnswer(claims=tuple(claims))
