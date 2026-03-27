import asyncio
import random
from typing import Any

import pandas as pd
from bofire.data_models.acquisition_functions.acquisition_function import AcquisitionFunction
from bofire.data_models.constraints.constraint import Constraint
from bofire.data_models.domain.constraints import Constraints
from bofire.data_models.domain.domain import Domain
from bofire.data_models.domain.features import Inputs, Outputs
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.categorical import CategoricalInput, CategoricalOutput
from bofire.data_models.features.continuous import ContinuousInput, ContinuousOutput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.surrogates.api import BotorchSurrogates

from eos.logging.logger import log
from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_ai_agent import BeaconAIAgent, round_floats
from eos.optimization.sequential_bayesian_optimizer import BayesianSequentialOptimizer

_PROBABILITY_TOLERANCE = 1e-9


class BeaconOptimizer(AbstractSequentialOptimizer):
    """
    Hybrid Bayesian + AI optimizer that probabilistically selects between a BoFire
    acquisition function and a reasoning AI at each sampling step."""

    InputType = ContinuousInput | DiscreteInput | CategoricalInput
    OutputType = ContinuousOutput | CategoricalOutput

    def __init__(
        self,
        inputs: list[InputType],
        outputs: list[OutputType],
        constraints: list[Constraint],
        acquisition_function: AcquisitionFunction,
        num_initial_samples: int,
        initial_sampling_method: SamplingMethodEnum = SamplingMethodEnum.SOBOL,
        surrogate_specs: BotorchSurrogates | None = None,
        # Beacon-specific
        ai_model: str = "claude-agent-sdk:sonnet",
        ai_api_key: str | None = None,
        p_bayesian: float = 0.5,
        p_ai: float = 0.5,
        ai_retries: int = 3,
        ai_history_size: int = 50,
        ai_model_settings: dict[str, Any] | None = None,
        ai_additional_parameters: list[str] | None = None,
        ai_additional_context: str | None = None,
        protocol_run_parameters_schedule: list[dict[str, dict[str, Any]]] | None = None,
    ):
        if abs(p_bayesian + p_ai - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError(f"p_bayesian ({p_bayesian}) + p_ai ({p_ai}) must equal 1.0")

        self._p_bayesian = p_bayesian
        self._p_ai = p_ai
        self._ai_history_size = ai_history_size
        self._ai_additional_context = ai_additional_context
        self._additional_parameters = set(ai_additional_parameters or [])

        # Store AI config so agent can be created/destroyed at runtime
        # (validated after _output_names is set below)
        self._ai_model = ai_model
        self._ai_api_key = ai_api_key
        self._ai_retries = ai_retries
        self._ai_model_settings = ai_model_settings
        self._protocol_context: str | None = None
        self._protocol_run_parameters_schedule = protocol_run_parameters_schedule

        self._domain = Domain(
            inputs=Inputs(features=inputs),
            outputs=Outputs(features=outputs),
            constraints=Constraints(constraints=constraints),
        )
        self._input_names = [f.key for f in self._domain.inputs.features]
        self._output_names = [f.key for f in self._domain.outputs.features]

        overlap = self._additional_parameters & set(self._output_names)
        if overlap:
            raise ValueError(f"ai_additional_parameters overlap with output names: {overlap}")

        # Compose the Bayesian optimizer
        self._bayesian_optimizer = BayesianSequentialOptimizer(
            inputs=inputs,
            outputs=outputs,
            constraints=constraints,
            acquisition_function=acquisition_function,
            num_initial_samples=num_initial_samples,
            initial_sampling_method=initial_sampling_method,
            surrogate_specs=surrogate_specs,
        )

        # Shared state (protected by _state_lock for concurrent access)
        self._history: list[dict[str, Any]] = []
        self._insights: list[str] = []
        self._state_lock = asyncio.Lock()
        self._journal: list[str] = []
        self._sample_journals: list[tuple[tuple, str | None]] = []  # (input_fingerprint, journal)
        self._num_samples_reported: int = 0

        # Only create the AI agent when needed
        self._ai_agent: BeaconAIAgent | None = None
        if p_ai > 0:
            self._ai_agent = self._create_ai_agent()

    def _create_ai_agent(self) -> BeaconAIAgent:
        agent = BeaconAIAgent(
            domain=self._domain,
            model=self._ai_model,
            api_key=self._ai_api_key,
            retries=self._ai_retries,
            model_settings=self._ai_model_settings,
            additional_context=self._ai_additional_context,
            protocol_run_parameters_schedule=self._protocol_run_parameters_schedule,
        )
        if self._protocol_context:
            agent.set_protocol_context(self._protocol_context)
        return agent

    def _input_key(self, row_dict: dict) -> tuple:
        """Create a hashable key from input parameter values for journal tracking."""
        return tuple(sorted((k, row_dict.get(k)) for k in self._input_names))

    def _tag_sample_journals(self, df: pd.DataFrame, journal: str | None) -> None:
        """Record the journal entry for each sampled row so report() can attribute correctly."""
        for _, row in df.iterrows():
            self._sample_journals.append((self._input_key(row.to_dict()), journal))

    async def sample(self, num_protocol_runs: int = 1) -> pd.DataFrame:
        use_ai = self._ai_agent is not None and random.random() < self._p_ai  # noqa: S311
        if use_ai:
            log.info(f"Beacon sampling {num_protocol_runs} protocol run(s) via AI")
            # Snapshot shared state under lock, then release for I/O-bound AI call
            async with self._state_lock:
                insights = list(self._insights)
                self._insights.clear()
                best_results = self._get_best_results()
                history = self._history[-self._ai_history_size :]
            try:
                df, journal_entry = await self._ai_agent.suggest_async(
                    num_protocol_runs,
                    history,
                    best_results,
                    insights,
                )
                async with self._state_lock:
                    self._journal.append(journal_entry)
                    self._tag_sample_journals(df, journal_entry)
                return df
            except Exception as e:
                log.warning(
                    f"Beacon AI failed ({type(e).__name__}: {e}), falling back to Bayesian sampling", exc_info=True
                )
                async with self._state_lock:
                    self._insights = insights + self._insights
                    loop = asyncio.get_running_loop()
                    df = await loop.run_in_executor(None, self._bayesian_optimizer.sample, num_protocol_runs)
                    self._tag_sample_journals(df, None)
                return df
        else:
            log.info(f"Beacon sampling {num_protocol_runs} protocol run(s) via Bayesian optimizer")
            async with self._state_lock:
                loop = asyncio.get_running_loop()
                df = await loop.run_in_executor(None, self._bayesian_optimizer.sample, num_protocol_runs)
                self._tag_sample_journals(df, None)
            return df

    async def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        async with self._state_lock:
            context_cols = [c for c in outputs_df.columns if c in self._additional_parameters]
            opt_outputs = outputs_df.drop(columns=context_cols) if context_cols else outputs_df
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._bayesian_optimizer.report, inputs_df, opt_outputs)

            combined = pd.concat([inputs_df, outputs_df], axis=1)
            for _, row in combined.iterrows():
                entry = row.to_dict()
                input_vals = {k: entry[k] for k in self._input_names}
                key = self._input_key(input_vals)
                journal = None
                for i, (stored_key, stored_journal) in enumerate(self._sample_journals):
                    if stored_key == key:
                        journal = stored_journal
                        del self._sample_journals[i]
                        break
                if journal:
                    entry["_beacon"] = {"journal": journal}
                self._history.append(entry)

            self._num_samples_reported += len(inputs_df)

            # Trim history to avoid unbounded growth
            if len(self._history) > self._ai_history_size:
                self._history = self._history[-self._ai_history_size :]

    def get_optimal_solutions(self) -> pd.DataFrame:
        return self._bayesian_optimizer.get_optimal_solutions()

    def get_input_names(self) -> list[str]:
        return self._input_names

    def get_output_names(self) -> list[str]:
        return self._output_names

    def get_additional_parameters(self) -> list[str]:
        return list(self._additional_parameters)

    def get_num_samples_reported(self) -> int:
        return self._num_samples_reported

    def set_protocol_context(self, protocol_yaml: str) -> None:
        self._protocol_context = protocol_yaml
        if self._ai_agent:
            self._ai_agent.set_protocol_context(protocol_yaml)

    def get_runtime_params(self) -> dict[str, Any]:
        return {
            "p_bayesian": self._p_bayesian,
            "p_ai": self._p_ai,
            "ai_history_size": self._ai_history_size,
            "ai_additional_context": self._ai_additional_context,
        }

    def set_runtime_params(self, params: dict[str, Any]) -> None:
        if "p_bayesian" in params:
            p_bayesian = float(params["p_bayesian"])
            p_ai = 1.0 - p_bayesian
            self._p_bayesian = p_bayesian
            self._p_ai = p_ai
            # Create AI agent on demand if enabling AI for first time
            if p_ai > 0 and self._ai_agent is None:
                self._ai_agent = self._create_ai_agent()
                log.info("Beacon AI agent created at runtime")
            # Tear down agent if AI disabled
            elif p_ai == 0 and self._ai_agent is not None:
                self._ai_agent = None
                log.info("Beacon AI agent torn down at runtime")
        if "ai_history_size" in params:
            val = int(params["ai_history_size"])
            if val < 1:
                raise ValueError(f"ai_history_size must be >= 1, got {val}")
            self._ai_history_size = val
        if "ai_additional_context" in params:
            self._ai_additional_context = params["ai_additional_context"] or None
            if self._ai_agent:
                self._ai_agent.additional_context = self._ai_additional_context

    def add_insight(self, insight: str) -> None:
        # Called from the Ray actor thread — use synchronous access since
        # asyncio.Lock can only be acquired from the event loop. The Ray actor
        # serializes sync method calls, so this is safe.
        self._insights.append(insight)
        self._journal.append(f"Expert insight received: {insight}")
        log.info(f"Beacon received expert insight: {insight}")

    def get_meta(self) -> dict[str, Any]:
        """Return serializable Beacon state for persistence."""
        return {
            "journal": self._journal,
            "insights": list(self._insights),
            "runtime_params": self.get_runtime_params(),
        }

    def restore_meta(self, meta: dict[str, Any]) -> None:
        """Restore Beacon state from persisted data."""
        self._journal = meta.get("journal", [])
        self._insights = meta.get("insights", [])

    def _get_best_results(self) -> list[dict[str, Any]]:
        if self._num_samples_reported == 0:
            return []
        try:
            pareto_df = self._bayesian_optimizer.get_optimal_solutions()
            return round_floats(pareto_df.to_dict(orient="records"))
        except Exception as e:
            log.warning(f"Failed to compute Pareto front for AI prompt: {type(e).__name__}: {e}")
            return []
