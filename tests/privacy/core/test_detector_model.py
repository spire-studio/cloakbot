from __future__ import annotations

import json

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from cloakbot.privacy.core.detection.detector_model import response_text


class _Out(BaseModel):
    entities: list = []


@pytest.mark.asyncio
async def test_response_text_recovers_final_model_text() -> None:
    payload = json.dumps({"entities": []})
    agent = Agent(output_type=NativeOutput(_Out), instructions="SYS", retries=1)
    result = await agent.run(
        "x",
        model=FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(payload)])),
    )
    assert result.output.entities == []
    # response_text recovers the model's final text part for the event log.
    assert response_text(result) == payload
