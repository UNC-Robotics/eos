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
_DISCRETE_INLINE_LIMIT = 20
_CONSTRAINT_TOLERANCE = 1e-6
_BACKOFF_MAX_ATTEMPTS = 3
_BACKOFF_MIN_SECONDS = 2
_BACKOFF_MAX_SECONDS = 30


class ExperimentSuggestion(BaseModel):
    parameters: dict[str, float | int | str]


class ExperimentSuggestions(BaseModel):
    suggestions: list[ExperimentSuggestion]
    journal_entry: str


@dataclass
class BeaconDeps:
    domain: Domain
    num_experiments: int
    history: list[dict[str, Any]]
    best_results: list[dict[str, Any]]
    insights: list[str]


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


def _build_example_section(domain: Domain) -> str:
    """Build a few-shot example showing the expected output format with actual parameter names."""
    example_params: dict[str, Any] = {}
    for feat in domain.inputs.features:
        if isinstance(feat, ContinuousInput):
            lo, hi = feat.bounds
            example_params[feat.key] = round((lo + hi) / 2, FLOAT_PRECISION)
        elif isinstance(feat, DiscreteInput):
            vals = feat.values
            example_params[feat.key] = vals[len(vals) // 2]
        elif isinstance(feat, CategoricalInput):
            example_params[feat.key] = feat.categories[0]

    example = {
        "suggestions": [{"parameters": example_params}],
        "journal_entry": "Iteration 1: Starting with a midpoint sample to establish a baseline.",
    }
    return "EXAMPLE OUTPUT (for 1 suggestion):\n" + json.dumps(example, indent=2)


def _get_journal(entry: dict[str, Any]) -> str | None:
    return (entry.get("_beacon") or {}).get("journal")


def _build_history_section(history: list[dict[str, Any]]) -> str:
    """
    Build the experimental history section, grouping experiments into rounds.

    Consecutive experiments with the same journal entry are grouped together.
    Experiments without a journal (e.g. from Bayesian sampling) form separate rounds.
    """
    lines: list[str] = [f"EXPERIMENTAL HISTORY ({len(history)} experiments):"]
    for round_num, (journal, group) in enumerate(groupby(history, key=_get_journal), 1):
        batch = [{k: v for k, v in e.items() if k != "_beacon"} for e in group]
        method = "AI" if journal else "Bayesian"
        lines.append(f"--- Round {round_num} ({method}) ---")
        if journal:
            lines.append(f"Journal: {journal}")
        lines.append(f"Experiments: {json.dumps(batch, indent=2)}")

    return "\n".join(lines)


def build_system_prompt(domain: Domain) -> str:
    """Translate a BoFire domain into natural-language instructions for the AI."""
    sections: list[str] = [
        "You are an expert experiment designer working in a sequential optimization loop. "
        "Each experiment is costly and time-consuming — your goal is to find optimal solutions "
        "in as few experiments as possible. You must return structured output matching the "
        "required schema exactly.",
        _build_input_section(domain),
        _build_objective_section(domain),
    ]

    constraint_section = _build_constraint_section(domain)
    if constraint_section:
        sections.append(constraint_section)

    sections.append(_build_example_section(domain))

    sections.append(
        "OPTIMIZATION STRATEGY:\n"
        "  1. EXPLORE AGGRESSIVELY: Default to exploration. Move 30-70% of parameter ranges between "
        "experiments. Push parameters to extremes — optima are often near boundaries. Small tweaks waste experiments.\n"
        "  2. MAXIMIZE INFORMATION: Every experiment should reveal something new. Test corners, edges, "
        "and extreme combinations. An experiment that confirms what you know is wasted.\n"
        "  3. USE DOMAIN KNOWLEDGE: Apply scientific expertise to predict promising regions and "
        "reason about cause-and-effect between parameters.\n"
        "  4. ANALYZE BUT DON'T OVERFIT: Study history for trends and interactions, but maintain "
        "skepticism about patterns until confirmed by multiple data points.\n"
        "  5. RESIST PREMATURE EXPLOITATION: Do not converge early. Keep exploring distant regions "
        "even when a promising area is found. Missing the global optimum is costlier than extra exploration.\n"
        "  6. NEVER REPEAT: Never suggest parameters identical or nearly identical to past experiments.\n"
        "  7. DIVERSIFY BATCHES: Spread suggestions across maximally different regions — never cluster.\n"
        "  8. ESCAPE PLATEAUS DECISIVELY: If results plateau, make radical changes to ALL parameters. "
        "Jump to unexplored regions. Try counterintuitive combinations.\n"
        "  9. THINK CONTRARIAN: Periodically test the opposite of your current hypothesis. "
        "The most valuable experiments challenge your assumptions.\n"
        "  10. RESPECT EXPERT INSIGHTS: When expert insights are provided, acknowledge them explicitly in your "
        "journal entry and incorporate them into your experimental design. Expert insights represent "
        "domain knowledge from the user — treat them as high-priority directives. If an insight "
        "conflicts with your current hypothesis, prioritize the insight and explain your reasoning. "
        "If you believe following an insight would be counterproductive, explain why in the journal "
        "but still design at least one experiment that follows the insight."
    )

    sections.append(
        "JOURNAL GUIDELINES:\n"
        "Your journal_entry should document:\n"
        "  - What patterns or trends you observe in the data so far\n"
        "  - What hypothesis you are testing with this batch of suggestions\n"
        "  - Why you chose these specific parameter values\n"
        "  - What you expect to learn from these experiments\n"
        "  - If expert insights were provided, explicitly state how you incorporated them"
    )

    sections.append(
        "RULES:\n"
        "  - All values must be within the specified bounds.\n"
        "  - All constraints must be satisfied.\n"
        "  - Parameter names must be EXACTLY as listed above, including dots "
        "(e.g. 'task.param', NOT 'task_param')."
    )

    return "\n\n".join(sections)


_CLAUDE_AGENT_SDK_PREFIX = "claude-agent-sdk:"


_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


def _set_api_key(model: str, api_key: str | None) -> None:
    """Set the appropriate environment variable for the model provider."""
    provider = model.split(":", maxsplit=1)[0] if ":" in model else ""

    # Ollama requires OLLAMA_BASE_URL; default to localhost if not set
    if provider == "ollama" and "OLLAMA_BASE_URL" not in os.environ:
        os.environ["OLLAMA_BASE_URL"] = _OLLAMA_DEFAULT_BASE_URL

    if api_key is None:
        return
    env_var_map = {
        "claude-agent-sdk": "ANTHROPIC_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "google-gla": "GOOGLE_API_KEY",
    }
    env_var = env_var_map.get(provider)
    if env_var:
        os.environ[env_var] = api_key


class BeaconAIAgent:
    def __init__(
        self,
        domain: Domain,
        model: str,
        api_key: str | None,
        retries: int,
        model_settings: dict[str, Any] | None = None,
        additional_context: str | None = None,
        experiment_parameters_schedule: list[dict[str, dict[str, Any]]] | None = None,
    ):
        _set_api_key(model, api_key)
        self._domain = domain
        self._input_names = [f.key for f in domain.inputs.features]
        static_prompt = build_system_prompt(domain)

        self._experiment_context: str | None = None
        self._additional_context: str | None = additional_context
        self._experiment_parameters_schedule = experiment_parameters_schedule

        resolved_model = model
        if model.startswith(_CLAUDE_AGENT_SDK_PREFIX):
            from eos.optimization.claude_agent_sdk_model import ClaudeAgentSDKModel  # noqa: PLC0415

            sdk_model_name = model[len(_CLAUDE_AGENT_SDK_PREFIX) :]
            max_thinking_tokens = model_settings.get("max_thinking_tokens") if model_settings else None
            resolved_model = ClaudeAgentSDKModel(
                model_name=sdk_model_name,
                max_thinking_tokens=max_thinking_tokens,
            )

        # Filter out SDK-specific keys before passing to Pydantic AI ModelSettings
        if isinstance(model_settings, str):
            model_settings = json.loads(model_settings) if model_settings.strip() else None
        sdk_keys = {"max_thinking_tokens"}
        filtered = {k: v for k, v in model_settings.items() if k not in sdk_keys} if model_settings else {}
        self._model_settings = ModelSettings(**filtered) if filtered else None

        self._agent: Agent[BeaconDeps, ExperimentSuggestions] = Agent(
            model=resolved_model,
            system_prompt=static_prompt,
            output_type=ExperimentSuggestions,
            deps_type=BeaconDeps,
            retries=retries,
        )

        @self._agent.system_prompt
        def dynamic_prompt(ctx: RunContext[BeaconDeps]) -> str:
            parts: list[str] = []

            if self._experiment_context:
                parts.append(f"EXPERIMENT DEFINITION (YAML):\n```\n{self._experiment_context}```")

            if self._additional_context:
                parts.append(f"ADDITIONAL CONTEXT:\n{self._additional_context}")

            if self._experiment_parameters_schedule:
                lines = ["PARAMETER SCHEDULE (fixed parameters for specific iterations):"]
                for i, params in enumerate(self._experiment_parameters_schedule):
                    lines.append(f"  Iteration {i}: {json.dumps(params)}")
                parts.append("\n".join(lines))

            if ctx.deps.best_results:
                parts.append(f"BEST RESULTS SO FAR:\n{json.dumps(ctx.deps.best_results, indent=2)}")

            if ctx.deps.history:
                parts.append(_build_history_section(ctx.deps.history))

            if ctx.deps.insights:
                parts.append(
                    "EXPERT INSIGHTS (HIGH PRIORITY — you MUST acknowledge these in your journal and "
                    "incorporate them into your experimental design):\n"
                    + "\n".join(f"  - {insight}" for insight in ctx.deps.insights)
                )

            total_experiments = len(ctx.deps.history)
            parts.append(
                f"You have {total_experiments} completed experiment(s) so far. "
                f"Please suggest {ctx.deps.num_experiments} new experiment(s)."
            )

            return "\n\n".join(parts)

        @self._agent.output_validator
        def validate_suggestions(
            ctx: RunContext[BeaconDeps],
            output: ExperimentSuggestions,
        ) -> ExperimentSuggestions:
            return _validate_suggestions(ctx, output)

    @property
    def additional_context(self) -> str | None:
        return self._additional_context

    @additional_context.setter
    def additional_context(self, value: str | None) -> None:
        self._additional_context = value

    def set_experiment_context(self, experiment_yaml: str) -> None:
        self._experiment_context = experiment_yaml

    def suggest(
        self,
        num_experiments: int,
        history: list[dict[str, Any]],
        best_results: list[dict[str, Any]],
        insights: list[str],
    ) -> tuple[pd.DataFrame, str]:
        deps = BeaconDeps(
            domain=self._domain,
            num_experiments=num_experiments,
            history=round_floats(history),
            best_results=round_floats(best_results),
            insights=insights,
        )
        result = self._run_with_backoff(deps)
        suggestions = result.output

        rows = []
        for s in suggestions.suggestions:
            row = {}
            for name in self._input_names:
                val = s.parameters[name]
                if isinstance(val, float):
                    val = round(val, FLOAT_PRECISION)
                row[name] = val
            rows.append(row)

        df = pd.DataFrame(rows, columns=self._input_names)
        return df, suggestions.journal_entry

    async def suggest_async(
        self,
        num_experiments: int,
        history: list[dict[str, Any]],
        best_results: list[dict[str, Any]],
        insights: list[str],
    ) -> tuple[pd.DataFrame, str]:
        """Async version of suggest() that yields during the LLM API call."""
        deps = BeaconDeps(
            domain=self._domain,
            num_experiments=num_experiments,
            history=round_floats(history),
            best_results=round_floats(best_results),
            insights=insights,
        )
        result = await self._run_with_backoff_async(deps)
        suggestions = result.output

        rows = []
        for s in suggestions.suggestions:
            row = {}
            for name in self._input_names:
                val = s.parameters[name]
                if isinstance(val, float):
                    val = round(val, FLOAT_PRECISION)
                row[name] = val
            rows.append(row)

        df = pd.DataFrame(rows, columns=self._input_names)
        return df, suggestions.journal_entry

    @retry(
        stop=stop_after_attempt(_BACKOFF_MAX_ATTEMPTS),
        wait=wait_exponential(min=_BACKOFF_MIN_SECONDS, max=_BACKOFF_MAX_SECONDS),
        retry=retry_if_not_exception_type(UnexpectedModelBehavior),
        before_sleep=before_sleep_log(log.logger, logging.WARNING),
        reraise=True,
    )
    def _run_with_backoff(self, deps: BeaconDeps) -> "AgentRunResult[ExperimentSuggestions]":
        """
        Run the agent with exponential backoff for transient API errors.

        Runs synchronously — acceptable because this executes inside a Ray actor (single-threaded).
        """
        return self._agent.run_sync("", deps=deps, model_settings=self._model_settings)

    @retry(
        stop=stop_after_attempt(_BACKOFF_MAX_ATTEMPTS),
        wait=wait_exponential(min=_BACKOFF_MIN_SECONDS, max=_BACKOFF_MAX_SECONDS),
        retry=retry_if_not_exception_type(UnexpectedModelBehavior),
        before_sleep=before_sleep_log(log.logger, logging.WARNING),
        reraise=True,
    )
    async def _run_with_backoff_async(self, deps: BeaconDeps) -> "AgentRunResult[ExperimentSuggestions]":
        """Async version with exponential backoff — yields during the LLM API call."""
        return await self._agent.run("", deps=deps, model_settings=self._model_settings)


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
    output: ExperimentSuggestions,
) -> ExperimentSuggestions:
    """Validate AI suggestions against the BoFire domain."""
    domain = ctx.deps.domain
    num_experiments = ctx.deps.num_experiments
    errors: list[str] = []

    if len(output.suggestions) != num_experiments:
        errors.append(f"Expected {num_experiments} suggestions, got {len(output.suggestions)}.")

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
