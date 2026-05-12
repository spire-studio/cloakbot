from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from cloakbot.privacy.core.sanitization.sanitize import remap_response, sanitize_tool_output
from cloakbot.privacy.core.state.vault import PLACEHOLDER_RE
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.tool_models import (
    ToolApprovalRequest,
    ToolApprovalRequiredError,
    ToolPrivacyClass,
    ToolPrivacyRecord,
)
from cloakbot.providers.base import ToolCallRequest
from cloakbot.utils.helpers import stringify_text_blocks

_MAX_RECORDED_OUTPUT_CHARS = 4000


class ToolPrivacyInterceptor:
    """Restore local tool inputs and sanitize tool outputs before model reuse."""

    def __init__(self, ctx: TurnContext) -> None:
        self._ctx = ctx

    async def prepare_tool_call(
        self,
        tool_call: ToolCallRequest,
        *,
        privacy_class: ToolPrivacyClass,
    ) -> ToolCallRequest:
        restored_arguments = await self._restore_value(tool_call.arguments)
        if privacy_class is not ToolPrivacyClass.LOCAL:
            sanitized_arguments, modified, entities = await self._sanitize_value(
                restored_arguments,
            )
            placeholder_sensitive = _contains_placeholder(tool_call.arguments)
            sensitive = modified or placeholder_sensitive
            if sensitive:
                self._ctx.tool_input_entities.extend(entities)
                request = ToolApprovalRequest(
                    approval_id=uuid4().hex,
                    session_key=self._ctx.session_key,
                    turn_id=self._ctx.turn_id,
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    privacy_class=privacy_class,
                    remote_arguments=_dict_or_empty(sanitized_arguments),
                    restored_arguments=_dict_or_empty(restored_arguments),
                    detected_entities=entities,
                )
                self._ctx.tool_approvals.append(request)
                raise ToolApprovalRequiredError(request)

        return ToolCallRequest(
            id=tool_call.id,
            name=tool_call.name,
            arguments=restored_arguments,
            extra_content=tool_call.extra_content,
            provider_specific_fields=tool_call.provider_specific_fields,
            function_provider_specific_fields=tool_call.function_provider_specific_fields,
        )

    async def sanitize_tool_result(
        self,
        tool_call: ToolCallRequest,
        result: Any,
        *,
        privacy_class: ToolPrivacyClass = ToolPrivacyClass.LOCAL,
    ) -> Any:
        sanitized, modified, entities = await self._sanitize_value(result)
        self._ctx.tool_output_entities.extend(entities)
        self._ctx.tool_results.append(
            ToolPrivacyRecord(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                privacy_class=privacy_class,
                remote_arguments=dict(tool_call.arguments),
                sanitized_output=_recorded_output_text(sanitized),
                was_sanitized=modified,
            )
        )
        return sanitized

    async def _restore_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return await remap_response(value, self._ctx.session_key)
        if isinstance(value, list):
            return [await self._restore_value(item) for item in value]
        if isinstance(value, dict):
            return {key: await self._restore_value(item) for key, item in value.items()}
        return value

    async def _sanitize_value(self, value: Any) -> tuple[Any, bool, list[Any]]:
        if isinstance(value, str):
            sanitized, modified, entities = await sanitize_tool_output(
                value,
                self._ctx.session_key,
                turn_id=self._ctx.turn_id,
            )
            return sanitized, modified, entities

        if isinstance(value, list):
            sanitized_items: list[Any] = []
            modified_any = False
            all_entities: list[Any] = []
            for item in value:
                sanitized_item, modified, entities = await self._sanitize_value(item)
                sanitized_items.append(sanitized_item)
                modified_any = modified_any or modified
                all_entities.extend(entities)
            return sanitized_items, modified_any, all_entities

        if isinstance(value, dict):
            sanitized_dict: dict[str, Any] = {}
            modified_any = False
            all_entities: list[Any] = []
            for key, item in value.items():
                sanitized_item, modified, entities = await self._sanitize_value(item)
                sanitized_dict[key] = sanitized_item
                modified_any = modified_any or modified
                all_entities.extend(entities)
            return sanitized_dict, modified_any, all_entities

        return value, False, []


def _recorded_output_text(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = stringify_text_blocks(value) or "(non-text tool output)"
    else:
        text = str(value)

    if len(text) > _MAX_RECORDED_OUTPUT_CHARS:
        return text[:_MAX_RECORDED_OUTPUT_CHARS] + "\n... (truncated)"
    return text


def _contains_placeholder(value: Any) -> bool:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return bool(PLACEHOLDER_RE.search(text))


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
