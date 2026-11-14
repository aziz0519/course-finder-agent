from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.answer_composer import OpenAIAnswerComposer
from app.retrieval.readings import Evidence


def _evidence() -> Evidence:
    return Evidence(
        document_title="Bohr model",
        course_code="PHYS 350",
        document_id="phys350-bohr-model",
        source_checksum="a" * 64,
        ingestion_version="b" * 24,
        page_number=4,
        section=("The Bohr atom",),
        excerpt="Figure 2 labels the second energy level as holding up to 8 electrons.",
        chunk_id="chunk-1",
        extraction_method="native",
        bbox=(1.0, 2.0, 3.0, 4.0),
    )


def test_openai_composer_returns_claim_with_valid_evidence_reference() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "claims": [
                                        {
                                            "text": "The figure labels capacity as up to eight.",
                                            "evidence_index": 0,
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            },
        )

    composer = OpenAIAnswerComposer(
        SecretStr("test-secret"),
        "test-model",
        transport=httpx.MockTransport(respond),
    )
    result = composer.compose("How many electrons?", (_evidence(),))

    assert result.claims[0].evidence_index == 0
    assert seen[0].headers["Authorization"] == "Bearer test-secret"
    request_payload = json.loads(seen[0].content)
    assert request_payload["max_completion_tokens"] <= 450
    assert "untrusted data" in request_payload["messages"][0]["content"]


def test_openai_composer_rejects_invalid_evidence_index() -> None:
    response_body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"claims": [{"text": "unsupported", "evidence_index": 2}]}
                    )
                }
            }
        ]
    }
    composer = OpenAIAnswerComposer(
        SecretStr("test-secret"),
        "test-model",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=response_body)
        ),
    )

    with pytest.raises(ValueError, match="outside the supplied set"):
        composer.compose("question", (_evidence(),))


def test_openai_composer_fails_closed_on_provider_error() -> None:
    composer = OpenAIAnswerComposer(
        SecretStr("test-secret"),
        "test-model",
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )

    with pytest.raises(ValueError, match="provider failed"):
        composer.compose("question", (_evidence(),))
