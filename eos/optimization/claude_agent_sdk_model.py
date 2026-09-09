"""
Custom Pydantic AI Model that delegates to the Claude Agent SDK.

This allows using Claude models via the Agent SDK (which authenticates via
~/.claude CLI credentials).
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.usage import RequestUsage

from collections.abc import Sequence

from eos.logging.logger import log


def _extract_instructions(messages: Sequence[ModelMessage]) -> str | None:
    """Extract system prompt instructions from Pydantic AI messages."""
    instructions: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            if msg.instructions:
                instructions.append(msg.instructions)
            for part in msg.parts:
                if isinstance(part, SystemPromptPart):
                    instructions.append(part.content)
    return "\n\n".join(instructions) if instructions else None


def _build_user_prompt(messages: Sequence[ModelMessage]) -> str:
    """
    Convert Pydantic AI messages into a single user prompt string.

    Extracts user prompts, tool returns, and retry prompts from all
    messages and concatenates them. Previous model responses are included
    for context during retries.
    """
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    if isinstance(part.content, str):
                        parts.append(part.content)
                    else:
                        parts.extend(item for item in part.content if isinstance(item, str))
                elif isinstance(part, ToolReturnPart):
                    parts.append(f"[Tool result for '{part.tool_name}']: {part.model_response_str()}")
                elif isinstance(part, RetryPromptPart):
                    parts.append(f"[Retry requested]: {part.model_response()}")
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    parts.append(f"[Previous response]: {part.content}")
                elif isinstance(part, ToolCallPart):
                    args_str = part.args if isinstance(part.args, str) else json.dumps(part.args)
                    parts.append(f"[Previous tool call '{part.tool_name}']: {args_str}")
    return "\n\n".join(parts)


def _to_request_usage(usage: dict[str, Any] | None) -> RequestUsage:
    """Map the Agent SDK's usage dict onto Pydantic AI's usage model."""
    if not usage:
        return RequestUsage()
    return RequestUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
    )


@dataclass(init=False)
class ClaudeAgentSDKModel(Model):
    """
    A Pydantic AI Model that uses the Claude Agent SDK for inference.

    The Agent SDK authenticates via Claude Code CLI credentials (~/.claude),
    so no API key is needed.
    """

    _sdk_model_name: str = field(repr=False)
    _full_model_name: str = field(repr=False)
    _effort: str | None = field(default=None, repr=False)

    def __init__(
        self,
        model_name: str = "sonnet",
        *,
        effort: str | None = None,
        profile: ModelProfile | None = None,
        settings: ModelSettings | None = None,
    ) -> None:
        self._sdk_model_name = model_name
        self._full_model_name = f"claude-agent-sdk:{model_name}"
        self._effort = effort

        if profile is None:
            profile = ModelProfile(
                supports_tools=True,
                supports_json_schema_output=False,
                default_structured_output_mode="tool",
            )
        super().__init__(settings=settings, profile=profile)

    @property
    def model_name(self) -> str:
        return self._full_model_name

    @property
    def system(self) -> str:
        return "claude-agent-sdk"

    async def _call_sdk(
        self,
        user_prompt: str,
        instructions: str | None,
        output_format: dict[str, Any] | None,
    ) -> tuple[str | None, Any, RequestUsage]:
        """Call the Claude Agent SDK and return (result_text, structured_output, usage)."""
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query  # noqa: PLC0415

        # Structured output uses an internal StructuredOutput tool call, which requires
        # at least 2 turns: one for the model to call the tool, one to process the result.
        # Code execution tools let the agent write and run scripts.
        allowed_tools = ["Bash", "Read", "Write"]
        max_turns = 8 if output_format else 5
        sdk_options = ClaudeAgentOptions(
            model=self._sdk_model_name,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            # No filesystem settings: CLAUDE.md and user settings are irrelevant here and would
            # change the cached prompt prefix from one machine to the next.
            setting_sources=[],
        )
        if instructions:
            sdk_options.system_prompt = instructions
        if output_format:
            sdk_options.output_format = output_format
        if self._effort is not None:
            sdk_options.effort = self._effort

        result_text: str | None = None
        structured_output: Any = None
        usage = RequestUsage()

        async for message in query(
            prompt=user_prompt or "Please provide your response.",
            options=sdk_options,
        ):
            if isinstance(message, ResultMessage):
                if message.structured_output is not None:
                    structured_output = message.structured_output
                if message.result is not None:
                    result_text = message.result
                if message.is_error:
                    raise UnexpectedModelBehavior(f"Claude Agent SDK returned an error: {message.result}")
                usage = _to_request_usage(message.usage)
                self._log_usage(message, usage)

        return result_text, structured_output, usage

    def _log_usage(self, message: Any, usage: RequestUsage) -> None:
        cached = usage.cache_read_tokens + usage.cache_write_tokens
        cache_hit = usage.cache_read_tokens / cached if cached else 0.0
        cost = f"${message.total_cost_usd:.4f}" if message.total_cost_usd is not None else "n/a"
        log.info(
            f"Beacon AI call: {usage.input_tokens} in / {usage.output_tokens} out, "
            f"cache {usage.cache_read_tokens} read / {usage.cache_write_tokens} write "
            f"({cache_hit:.0%} hit), {message.num_turns} turn(s), {cost}"
        )

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        model_settings, model_request_parameters = self.prepare_request(model_settings, model_request_parameters)

        # Instructions are the stable prefix, so they stay cached across calls and campaigns.
        instructions = _extract_instructions(messages)
        user_prompt = _build_user_prompt(messages)

        output_format: dict[str, Any] | None = None
        output_tool = None
        if model_request_parameters.output_tools:
            output_tool = model_request_parameters.output_tools[0]
            output_format = {
                "type": "json_schema",
                "schema": output_tool.parameters_json_schema,
            }

        try:
            result_text, structured_output, usage = await self._call_sdk(user_prompt, instructions, output_format)
        except (UnexpectedModelBehavior, ImportError):
            raise
        except Exception as e:
            raise UnexpectedModelBehavior(f"Claude Agent SDK error: {type(e).__name__}: {e}") from e

        response_parts: list[TextPart | ToolCallPart] = []
        if structured_output is not None and output_tool is not None:
            args = structured_output if isinstance(structured_output, dict) else json.loads(str(structured_output))
            response_parts.append(ToolCallPart(tool_name=output_tool.name, args=args))
        elif result_text:
            response_parts.append(TextPart(content=result_text))
        else:
            raise UnexpectedModelBehavior("Claude Agent SDK returned no response")

        return ModelResponse(
            parts=response_parts,
            model_name=self._full_model_name,
            timestamp=datetime.now(tz=UTC),
            usage=usage,
        )
