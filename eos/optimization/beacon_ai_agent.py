import json
import logging
import os
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING, Any

import pandas as pd
from bofire.data_models.constraints.linear import LinearEqualityConstraint, LinearInequalityConstraint
from bofire.data_models.features.categorical import CategoricalInput
from bofire.data_models.features.continuous import ContinuousInput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.objectives.identity import MaximizeObjective, MinimizeObjective
from bofire.data_models.objectives.target import CloseToTargetObjective
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings
from tenacity import before_sleep_log, retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from eos.logging.logger import log

from bofire.data_models.domain.domain import Domain

if TYPE_CHECKING:
    from pydantic_ai.result import AgentRunResult

FLOAT_PRECISION = 5
# History is only read for trends, so it renders coarser than the values Beacon returns.
_HISTORY_FLOAT_PRECISION = 4
_DISCRETE_INLINE_LIMIT = 20
_CONSTRAINT_TOLERANCE = 1e-6
_BACKOFF_MAX_ATTEMPTS = 3
_BACKOFF_MIN_SECONDS = 2
_BACKOFF_MAX_SECONDS = 30


class ProtocolRunSuggestion(BaseModel):
    parameters: dict[str, float | int | str]


class ProtocolRunSuggestions(BaseModel):
    suggestions: list[ProtocolRunSuggestion]
    journal_entry: str


@dataclass
class BeaconDeps:
    domain: Domain
    num_protocol_runs: int
    history: list[dict[str, Any]]
    best_results: list[dict[str, Any]]
    insights: list[str]
    total_runs: int = 0


def round_floats(value: Any) -> Any:
    """Round any float to FLOAT_PRECISION decimal places, recursing into dicts and lists."""
    if isinstance(value, float):
        return round(value, FLOAT_PRECISION)
    if isinstance(value, dict):
        return {k: round_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v) for v in value]
    return value


def _build_input_section(domain: Domain) -> str:
    """Build the input parameters section of the system prompt."""
    lines: list[str] = ["INPUT PARAMETERS:"]
    for feat in domain.inputs.features:
        if isinstance(feat, ContinuousInput):
            lo = round(feat.bounds[0], FLOAT_PRECISION)
            hi = round(feat.bounds[1], FLOAT_PRECISION)
            line = f"  - {feat.key}: continuous, bounds [{lo}, {hi}]"
            if feat.stepsize is not None:
                line += f", stepsize {feat.stepsize}"
            lines.append(line)
        elif isinstance(feat, DiscreteInput):
            vals = feat.values
            if len(vals) > _DISCRETE_INLINE_LIMIT:
                lines.append(f"  - {feat.key}: discrete, range [{min(vals)}, {max(vals)}] ({len(vals)} values)")
            else:
                lines.append(f"  - {feat.key}: discrete, allowed values {vals}")
        elif isinstance(feat, CategoricalInput):
            lines.append(f"  - {feat.key}: categorical, categories {feat.categories}")
    return "\n".join(lines)


def _build_objective_section(domain: Domain) -> str:
    """Build the objectives section of the system prompt."""
    lines: list[str] = ["OBJECTIVES:"]
    for feat in domain.outputs.features:
        obj = feat.objective
        if isinstance(obj, MinimizeObjective):
            lines.append(f"  - {feat.key}: MINIMIZE (weight {obj.w})")
        elif isinstance(obj, MaximizeObjective):
            lines.append(f"  - {feat.key}: MAXIMIZE (weight {obj.w})")
        elif isinstance(obj, CloseToTargetObjective):
            lines.append(f"  - {feat.key}: TARGET {obj.target} (weight {obj.w})")
    return "\n".join(lines)


def _format_linear_terms(c: LinearEqualityConstraint | LinearInequalityConstraint) -> str:
    return " + ".join(f"{coef}*{feat}" for coef, feat in zip(c.coefficients, c.features, strict=True))


def _build_constraint_section(domain: Domain) -> str | None:
    """Build the constraints section of the system prompt, or None if no constraints."""
    if not domain.constraints or not domain.constraints.constraints:
        return None
    lines: list[str] = ["CONSTRAINTS:"]
    for c in domain.constraints.constraints:
        if isinstance(c, LinearEqualityConstraint):
            lines.append(f"  - {_format_linear_terms(c)} = {c.rhs}")
        elif isinstance(c, LinearInequalityConstraint):
            lines.append(f"  - {_format_linear_terms(c)} <= {c.rhs}")
        else:
            lines.append(f"  - {json.dumps(c.model_dump(), default=str)}")
    return "\n".join(lines)


def _get_journal(entry: dict[str, Any]) -> str | None:
    return (entry.get("_beacon") or {}).get("journal")


def _format_cell(value: Any) -> str:
    """Render one table cell, trimming float noise that costs tokens and carries no information."""
    if isinstance(value, float):
        return f"{round(value, _HISTORY_FLOAT_PRECISION):g}"
    return "" if value is None else str(value)


def _build_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Render rows as TSV. Far cheaper than indented JSON, which repeats every key on every row."""
    lines = ["\t".join(columns)]
    lines.extend("\t".join(_format_cell(row.get(c)) for c in columns) for row in rows)
    return "\n".join(lines)


def _build_history_section(history: list[dict[str, Any]], columns: list[str]) -> str:
    """
    Build the experimental history section, grouping protocols into rounds.

    Consecutive protocols with the same journal entry are grouped together.
    Experiments without a journal (e.g. from Bayesian sampling) form separate rounds.
    """
    lines: list[str] = [f"EXPERIMENTAL HISTORY ({len(history)} protocols, tab-separated):"]
    for round_num, (journal, group) in enumerate(groupby(history, key=_get_journal), 1):
        batch = [{k: v for k, v in e.items() if k != "_beacon"} for e in group]
        method = "AI" if journal else "Bayesian"
        lines.append(f"--- Round {round_num} ({method}) ---")
        if journal:
            lines.append(f"Journal: {journal}")
        lines.append(_build_table(batch, columns))

    return "\n".join(lines)


def build_system_prompt(domain: Domain) -> str:
    """Translate a BoFire domain into natural-language instructions for the AI."""
    sections: list[str] = [
        "You are an expert experiment designer working in a sequential optimization loop. "
        "Each experiment is costly and time-consuming — your goal is to find optimal solutions "
        "in as few protocols as possible. You must return structured output matching the "
        "required schema exactly.",
        _build_input_section(domain),
        _build_objective_section(domain),
    ]

    constraint_section = _build_constraint_section(domain)
    if constraint_section:
        sections.append(constraint_section)

    sections.append(
        "STRATEGY:\n"
        "  - Explore broadly before exploiting. Optima are often near boundaries, and batched "
        "suggestions should cover distinct regions rather than cluster.\n"
        "  - Never repeat or nearly repeat a past experiment.\n"
        "  - Apply scientific reasoning about cause and effect between parameters.\n"
        "  - Read history for trends, but stay skeptical of patterns until several points confirm "
        "them. If results plateau, change course sharply.\n"
        "  - Prioritize expert insights over your own hypotheses and acknowledge them in the "
        "journal. If you disagree, say why, but still test the insight."
    )

    sections.append(
        "JOURNAL FORMAT: markdown, LaTeX for math (e.g. $x^2$). Head it "
        "`## Run {N}` (or `## Runs {N}-{M}`) and use three sections:\n"
        "  ### Observations — patterns, trends and surprises in past runs; on the first run, your "
        "prior assumptions about the system instead.\n"
        "  ### Hypotheses — each grounded in an observation above, flagged as new, carried over or "
        "revised.\n"
        "  ### Actions — what this batch tests, and which hypothesis each experiment targets."
    )

    sections.append(
        "RULES:\n"
        "  - Every value must be within bounds and satisfy every constraint.\n"
        "  - Parameter names must be EXACTLY as listed above, including dots "
        "(e.g. 'task.param', NOT 'task_param')."
    )

    return "\n\n".join(sections)


_CLAUDE_AGENT_SDK_PREFIX = "claude-agent-sdk:"
_OLLAMA_PREFIX = "ollama:"
_SUPPORTED_MODEL_PREFIXES = (_CLAUDE_AGENT_SDK_PREFIX, _OLLAMA_PREFIX)

_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


def _validate_model(model: str) -> None:
    """Beacon supports the Claude Agent SDK and Ollama only."""
    if not model.startswith(_SUPPORTED_MODEL_PREFIXES):
        raise ValueError(
            f"Unsupported Beacon AI model '{model}'. "
            f"Model must start with one of: {', '.join(_SUPPORTED_MODEL_PREFIXES)}"
        )


def _set_api_key(model: str, api_key: str | None) -> None:
    """Set the appropriate environment variable for the model provider."""
    # Ollama requires OLLAMA_BASE_URL, default to localhost if not set
    if model.startswith(_OLLAMA_PREFIX) and "OLLAMA_BASE_URL" not in os.environ:
        os.environ["OLLAMA_BASE_URL"] = _OLLAMA_DEFAULT_BASE_URL

    if api_key is not None and model.startswith(_CLAUDE_AGENT_SDK_PREFIX):
        os.environ["ANTHROPIC_API_KEY"] = api_key


def _resolve_model(model: str, model_settings: dict[str, Any] | None) -> tuple[Any, bool]:
    """Resolve the model string to a Pydantic AI model instance."""
    if not model.startswith(_CLAUDE_AGENT_SDK_PREFIX):
        return model, False
    from eos.optimization.claude_agent_sdk_model import ClaudeAgentSDKModel  # noqa: PLC0415

    sdk_model_name = model[len(_CLAUDE_AGENT_SDK_PREFIX) :]
    effort = model_settings.get("effort") if model_settings else None
    return ClaudeAgentSDKModel(model_name=sdk_model_name, effort=effort), True


class BeaconAIAgent:
    def __init__(
        self,
        domain: Domain,
        model: str,
        api_key: str | None,
        retries: int,
        model_settings: dict[str, Any] | None = None,
        additional_context: str | None = None,
        protocol_run_parameters_schedule: list[dict[str, dict[str, Any]]] | None = None,
    ):
        _validate_model(model)
        _set_api_key(model, api_key)
        self._domain = domain
        self._input_names = [f.key for f in domain.inputs.features]
        static_prompt = build_system_prompt(domain)

        self._protocol_context: str | None = None
        self._additional_context: str | None = additional_context
        self._protocol_run_parameters_schedule = protocol_run_parameters_schedule

        if isinstance(model_settings, str):
            model_settings = json.loads(model_settings) if model_settings.strip() else None

        resolved_model, self._code_execution = _resolve_model(model, model_settings)

        # Filter out SDK-specific keys before passing to Pydantic AI ModelSettings
        sdk_keys = {"effort"}
        filtered = {k: v for k, v in model_settings.items() if k not in sdk_keys} if model_settings else {}
        self._model_settings = ModelSettings(**filtered) if filtered else None

        self._agent: Agent[BeaconDeps, ProtocolRunSuggestions] = Agent(
            model=resolved_model,
            system_prompt=static_prompt,
            output_type=ProtocolRunSuggestions,
            deps_type=BeaconDeps,
            retries=retries,
        )
        self._register_dynamic_prompt()

    def _register_dynamic_prompt(self) -> None:
        """Register the campaign-scoped system prompt and output validator on the agent."""

        @self._agent.system_prompt
        def campaign_prompt(ctx: RunContext[BeaconDeps]) -> str:
            """
            Content that is fixed for the life of a campaign, so it stays in the cached prefix.

            Per-suggestion content belongs in the user prompt instead — anything that changes here
            invalidates the cache for everything after it.
            """
            parts: list[str] = []

            if self._protocol_context:
                parts.append(f"EXPERIMENT DEFINITION (YAML):\n```\n{self._protocol_context}```")

            if self._additional_context:
                parts.append(f"ADDITIONAL CONTEXT:\n{self._additional_context}")

            if self._protocol_run_parameters_schedule:
                lines = ["PARAMETER SCHEDULE (fixed parameters for specific iterations):"]
                for i, params in enumerate(self._protocol_run_parameters_schedule):
                    lines.append(f"  Iteration {i}: {json.dumps(params)}")
                parts.append("\n".join(lines))

            if self._code_execution:
                parts.append(
                    "CODE EXECUTION: You can write and run Python scripts (Bash, Read, Write tools) "
                    "to analyze experimental data — useful for statistical analysis, trend detection, "
                    "and identifying non-obvious patterns."
                )

            return "\n\n".join(parts)

        @self._agent.output_validator
        def validate_suggestions(
            ctx: RunContext[BeaconDeps],
            output: ProtocolRunSuggestions,
        ) -> ProtocolRunSuggestions:
            return _validate_suggestions(ctx, output)

    def _history_columns(self, history: list[dict[str, Any]]) -> list[str]:
        """Table columns: domain inputs, then outputs, then any additional parameters carried along."""
        columns = list(self._input_names) + [f.key for f in self._domain.outputs.features]
        known = set(columns)
        for entry in history:
            for key in entry:
                if key != "_beacon" and key not in known:
                    known.add(key)
                    columns.append(key)
        return columns

    def _build_user_prompt(self, deps: BeaconDeps) -> str:
        """
        Build the per-suggestion prompt.

        Everything that changes between suggestions lives here rather than in the system prompt, so
        the cached prefix survives from one call to the next.
        """
        parts: list[str] = []

        if deps.history:
            columns = self._history_columns(deps.history)
            parts.append(_build_history_section(deps.history, columns))

        if deps.best_results:
            columns = self._history_columns(deps.best_results)
            parts.append("BEST RESULTS SO FAR (tab-separated):\n" + _build_table(deps.best_results, columns))

        if deps.insights:
            parts.append("EXPERT INSIGHTS:\n" + "\n".join(f"  - {insight}" for insight in deps.insights))

        parts.append(
            f"You have {deps.total_runs} completed experiment(s) so far. "
            f"Please suggest {deps.num_protocol_runs} new experiment(s)."
        )

        return "\n\n".join(parts)

    @property
    def additional_context(self) -> str | None:
        return self._additional_context

    @additional_context.setter
    def additional_context(self, value: str | None) -> None:
        self._additional_context = value

    def set_protocol_context(self, protocol_yaml: str) -> None:
        self._protocol_context = protocol_yaml

    def _build_deps(
        self,
        num_protocol_runs: int,
        history: list[dict[str, Any]],
        best_results: list[dict[str, Any]],
        insights: list[str],
        total_runs: int | None,
    ) -> BeaconDeps:
        return BeaconDeps(
            domain=self._domain,
            num_protocol_runs=num_protocol_runs,
            history=round_floats(history),
            best_results=round_floats(best_results),
            insights=insights,
            total_runs=len(history) if total_runs is None else total_runs,
        )

    def suggest(
        self,
        num_protocol_runs: int,
        history: list[dict[str, Any]],
        best_results: list[dict[str, Any]],
        insights: list[str],
        total_runs: int | None = None,
    ) -> tuple[pd.DataFrame, str]:
        deps = self._build_deps(num_protocol_runs, history, best_results, insights, total_runs)
        result = self._run_with_backoff(deps)
        return self._format_suggestions(result.output)

    async def suggest_async(
        self,
        num_protocol_runs: int,
        history: list[dict[str, Any]],
        best_results: list[dict[str, Any]],
        insights: list[str],
        total_runs: int | None = None,
    ) -> tuple[pd.DataFrame, str]:
        """Async version of suggest() that yields during the LLM API call."""
        deps = self._build_deps(num_protocol_runs, history, best_results, insights, total_runs)
        result = await self._run_with_backoff_async(deps)
        return self._format_suggestions(result.output)

    def _format_suggestions(self, suggestions: ProtocolRunSuggestions) -> tuple[pd.DataFrame, str]:
        rows = [
            {name: round_floats(suggestion.parameters[name]) for name in self._input_names}
            for suggestion in suggestions.suggestions
        ]
        df = pd.DataFrame(rows, columns=self._input_names)
        return df, suggestions.journal_entry

    @retry(
        stop=stop_after_attempt(_BACKOFF_MAX_ATTEMPTS),
        wait=wait_exponential(min=_BACKOFF_MIN_SECONDS, max=_BACKOFF_MAX_SECONDS),
        retry=retry_if_not_exception_type(UnexpectedModelBehavior),
        before_sleep=before_sleep_log(log.logger, logging.WARNING),
        reraise=True,
    )
    def _run_with_backoff(self, deps: BeaconDeps) -> "AgentRunResult[ProtocolRunSuggestions]":
        """
        Run the agent with exponential backoff for transient API errors.

        Runs synchronously — acceptable because this executes inside a Ray actor (single-threaded).
        """
        return self._agent.run_sync(self._build_user_prompt(deps), deps=deps, model_settings=self._model_settings)

    @retry(
        stop=stop_after_attempt(_BACKOFF_MAX_ATTEMPTS),
        wait=wait_exponential(min=_BACKOFF_MIN_SECONDS, max=_BACKOFF_MAX_SECONDS),
        retry=retry_if_not_exception_type(UnexpectedModelBehavior),
        before_sleep=before_sleep_log(log.logger, logging.WARNING),
        reraise=True,
    )
    async def _run_with_backoff_async(self, deps: BeaconDeps) -> "AgentRunResult[ProtocolRunSuggestions]":
        """Async version with exponential backoff — yields during the LLM API call."""
        return await self._agent.run(self._build_user_prompt(deps), deps=deps, model_settings=self._model_settings)


def _validate_and_coerce_feature(
    feat: ContinuousInput | DiscreteInput | CategoricalInput,
    key: str,
    val: Any,
    prefix: str,
    params: dict[str, Any],
) -> str | None:
    """Validate a single feature value. Returns an error string or None."""
    if isinstance(feat, ContinuousInput):
        try:
            fval = float(val)
        except (TypeError, ValueError):
            return f"{prefix}: '{key}' must be a number, got {val!r}."
        lo, hi = feat.bounds
        if not (lo <= fval <= hi):
            return f"{prefix}: '{key}' = {fval} is out of bounds [{lo}, {hi}]."
        params[key] = round(fval, FLOAT_PRECISION)
    elif isinstance(feat, DiscreteInput):
        try:
            fval = float(val)
        except (TypeError, ValueError):
            return f"{prefix}: '{key}' must be a number, got {val!r}."
        if fval not in feat.values:
            return f"{prefix}: '{key}' = {fval} is not in allowed values."
        params[key] = fval
    elif isinstance(feat, CategoricalInput):
        sval = str(val)
        if sval not in feat.categories:
            return f"{prefix}: '{key}' = {sval!r} is not in allowed categories {feat.categories}."
        params[key] = sval
    return None


def _validate_linear_constraints(domain: Domain, params: dict[str, Any], prefix: str) -> list[str]:
    """Validate linear constraints for a suggestion. Returns list of error strings."""
    errors: list[str] = []
    if not domain.constraints:
        return errors
    for c in domain.constraints.constraints:
        if not isinstance(c, LinearEqualityConstraint | LinearInequalityConstraint):
            continue
        try:
            lhs = sum(coef * float(params.get(feat, 0)) for coef, feat in zip(c.coefficients, c.features, strict=True))
        except (TypeError, ValueError):
            continue
        terms = _format_linear_terms(c)
        if isinstance(c, LinearEqualityConstraint) and abs(lhs - c.rhs) > _CONSTRAINT_TOLERANCE:
            errors.append(f"{prefix}: constraint {terms} = {c.rhs} not satisfied (got {lhs}).")
        elif isinstance(c, LinearInequalityConstraint) and lhs > c.rhs + _CONSTRAINT_TOLERANCE:
            errors.append(f"{prefix}: constraint {terms} <= {c.rhs} not satisfied (got {lhs}).")
    return errors


def _canonicalize(key: str) -> str:
    """Reduce a key to a canonical form for fuzzy matching."""
    return key.lower().replace(".", "_").replace("-", "_").replace(" ", "_")


def _normalize_param_keys(params: dict[str, Any], valid_keys: set[str]) -> dict[str, Any]:
    """
    Map AI-produced parameter keys back to the canonical task.parameter format from the domain.

    AI models commonly mangle dotted keys (e.g. 'task.param' -> 'task_param', 'Task_Param', 'task-param').
    We canonicalize both sides and match, always returning the exact domain key.
    """
    if all(k in valid_keys for k in params):
        return params
    lookup = {_canonicalize(k): k for k in valid_keys}
    normalized: dict[str, Any] = {}
    for k, v in params.items():
        canon = _canonicalize(k)
        if canon in lookup:
            normalized[lookup[canon]] = v
        else:
            normalized[k] = v
    return normalized


def _validate_suggestions(
    ctx: RunContext[BeaconDeps],
    output: ProtocolRunSuggestions,
) -> ProtocolRunSuggestions:
    """Validate AI suggestions against the BoFire domain."""
    domain = ctx.deps.domain
    num_protocol_runs = ctx.deps.num_protocol_runs
    errors: list[str] = []

    if len(output.suggestions) != num_protocol_runs:
        errors.append(f"Expected {num_protocol_runs} suggestions, got {len(output.suggestions)}.")

    valid_input_keys = {f.key for f in domain.inputs.features}
    feature_map = {f.key: f for f in domain.inputs.features}

    for i, suggestion in enumerate(output.suggestions):
        prefix = f"Suggestion {i + 1}"
        suggestion.parameters = _normalize_param_keys(suggestion.parameters, valid_input_keys)
        params = suggestion.parameters

        missing = valid_input_keys - set(params.keys())
        if missing:
            errors.append(f"{prefix}: missing parameters {missing}.")

        extra = set(params.keys()) - valid_input_keys
        if extra:
            errors.append(f"{prefix}: unexpected parameters {extra}.")

        for key, feat in feature_map.items():
            if key not in params:
                continue
            error = _validate_and_coerce_feature(feat, key, params[key], prefix, params)
            if error:
                errors.append(error)

        errors.extend(_validate_linear_constraints(domain, params, prefix))

    if errors:
        msg = "Your suggestions have the following issues:\n- " + "\n- ".join(errors)
        log.warning(f"Beacon AI validation retry: {msg}")
        raise ModelRetry(msg)

    return output
