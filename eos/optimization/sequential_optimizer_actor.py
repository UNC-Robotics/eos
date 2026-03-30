import asyncio
from typing import Any

import pandas as pd
import ray

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer


async def _maybe_await(result) -> Any:
    """Await the result if it's a coroutine, otherwise return it directly."""
    if asyncio.iscoroutine(result):
        return await result
    return result


@ray.remote
class SequentialOptimizerActor(AbstractSequentialOptimizer):
    def __init__(self, constructor_args: dict[str, Any], optimizer_type: type[AbstractSequentialOptimizer]):
        protocol_context = constructor_args.pop("protocol_context", None)
        self.optimizer = optimizer_type(**constructor_args)
        if protocol_context and hasattr(self.optimizer, "set_protocol_context"):
            self.optimizer.set_protocol_context(protocol_context)

    async def sample(self, num_protocol_runs: int = 1) -> pd.DataFrame:
        return await _maybe_await(self.optimizer.sample(num_protocol_runs))

    async def sample_and_get_meta(self, num_protocol_runs: int = 1) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        df = await _maybe_await(self.optimizer.sample(num_protocol_runs))
        meta = self.optimizer.get_meta() if hasattr(self.optimizer, "get_meta") else None
        return df, meta

    async def report(self, input_df: pd.DataFrame, output_df: pd.DataFrame) -> None:
        await _maybe_await(self.optimizer.report(input_df, output_df))

    async def report_and_get_meta(self, input_df: pd.DataFrame, output_df: pd.DataFrame) -> dict[str, Any] | None:
        await _maybe_await(self.optimizer.report(input_df, output_df))
        if hasattr(self.optimizer, "get_meta"):
            return self.optimizer.get_meta()
        return None

    def get_optimal_solutions(self) -> pd.DataFrame:
        return self.optimizer.get_optimal_solutions()

    def get_input_names(self) -> list[str]:
        return self.optimizer.get_input_names()

    def get_output_names(self) -> list[str]:
        return self.optimizer.get_output_names()

    def get_additional_parameters(self) -> list[str]:
        if hasattr(self.optimizer, "get_additional_parameters"):
            return self.optimizer.get_additional_parameters()
        return []

    def get_num_samples_reported(self) -> int:
        return self.optimizer.get_num_samples_reported()

    def get_optimizer_type(self) -> str:
        return type(self.optimizer).__name__

    def get_runtime_params(self) -> dict[str, Any]:
        if hasattr(self.optimizer, "get_runtime_params"):
            return self.optimizer.get_runtime_params()
        return {}

    def set_runtime_params(self, params: dict[str, Any]) -> None:
        if hasattr(self.optimizer, "set_runtime_params"):
            self.optimizer.set_runtime_params(params)

    def add_insight(self, insight: str) -> None:
        if hasattr(self.optimizer, "add_insight"):
            self.optimizer.add_insight(insight)

    def get_optimizer_meta(self) -> dict[str, Any] | None:
        if hasattr(self.optimizer, "get_meta"):
            return self.optimizer.get_meta()
        return None

    def restore_optimizer_meta(self, meta: dict[str, Any]) -> None:
        if hasattr(self.optimizer, "restore_meta"):
            self.optimizer.restore_meta(meta)
