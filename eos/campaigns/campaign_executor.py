import asyncio
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, TYPE_CHECKING

import pandas as pd
from ray.actor import ActorHandle
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.campaigns.entities.campaign import CampaignStatus, Campaign, CampaignSubmission
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRunSubmission
from eos.protocols.exceptions import EosProtocolRunCancellationError
from eos.protocols.protocol_executor_factory import ProtocolExecutorFactory
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.tasks.task_manager import TaskManager
from eos.utils import dict_utils

if TYPE_CHECKING:
    from eos.protocols.protocol_executor import ProtocolExecutor


class OptimizerState(Enum):
    """States for the campaign optimizer lifecycle."""

    UNINITIALIZED = auto()
    NEEDS_RESTORATION = auto()
    READY = auto()


@dataclass
class _PendingOptimizerSample:
    future: asyncio.Task
    protocol_runs: list[tuple[str, dict]]


async def _await_ray_ref(ref: Any) -> Any:
    """Wrap an awaitable Ray ObjectRef in a coroutine so it can be used with asyncio.create_task()."""
    return await ref


def _merge_protocol_run_params(base: dict[str, Any], overrides: dict[str, Any] | None) -> None:
    """Deep-merge protocol run parameter overrides into base parameters (mutates base)."""
    if overrides:
        for task_name, task_params in overrides.items():
            if task_name in base:
                base[task_name].update(task_params)
            else:
                base[task_name] = task_params


class CampaignExecutor:
    def __init__(
        self,
        campaign_submission: CampaignSubmission,
        campaign_manager: CampaignManager,
        campaign_optimizer_manager: CampaignOptimizerManager,
        task_manager: TaskManager,
        protocol_executor_factory: ProtocolExecutorFactory,
        protocol_run_manager: ProtocolRunManager,
        db_interface: AbstractSqlDbInterface,
    ):
        self._campaign_submission = campaign_submission
        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._task_manager = task_manager
        self._protocol_executor_factory = protocol_executor_factory
        self._protocol_run_manager = protocol_run_manager
        self._db_interface = db_interface

        # Campaign state
        self._campaign_name = campaign_submission.name
        self._protocol = campaign_submission.protocol
        self._campaign_status: CampaignStatus | None = None
        self._protocol_executors: dict[str, ProtocolExecutor] = {}
        self._pending_protocol_run_cancellations: set[str] = set()

        # Optimizer state
        self._optimizer: ActorHandle | None = None
        self._optimizer_input_names: list[str] = []
        self._optimizer_output_names: list[str] = []
        self._optimizer_additional_parameters: list[str] = []
        self._optimizer_state: OptimizerState = OptimizerState.UNINITIALIZED

        # Pending async optimizer operations
        self._pending_samples: list[_PendingOptimizerSample] = []
        self._pending_report: asyncio.Task | None = None
        self._pending_pareto: asyncio.Task | None = None
        self._queued_reports: list[tuple[pd.DataFrame, pd.DataFrame]] = []

    async def start_campaign(self, db: AsyncDbSession) -> None:
        """Initialize and start a new campaign or resume an existing one."""
        campaign = await self._campaign_manager.get_campaign(db, self._campaign_name)

        if campaign:
            await self._handle_existing_campaign(db, campaign)
        else:
            await self._initialize_new_campaign(db)

        await self._campaign_manager.start_campaign(db, self._campaign_name)

        self._campaign_status = CampaignStatus.RUNNING
        log.info(f"Started campaign '{self._campaign_name}'")

    async def _initialize_new_campaign(self, db: AsyncDbSession) -> None:
        """Create and initialize a new campaign."""
        await self._campaign_manager.create_campaign(db, self._campaign_submission)

    async def _handle_existing_campaign(self, db: AsyncDbSession, campaign: Campaign) -> None:
        """Handle resuming or rejecting an existing campaign based on its state."""
        self._campaign_status = campaign.status

        if not self._campaign_submission.resume:
            self._validate_campaign_resumption(campaign.status)

        await self._resume_campaign(db)

    def _validate_campaign_resumption(self, status: CampaignStatus) -> None:
        """Validate if a campaign can be resumed based on its status."""
        invalid_statuses = {
            CampaignStatus.COMPLETED: "completed",
            CampaignStatus.SUSPENDED: "suspended",
            CampaignStatus.CANCELLED: "cancelled",
            CampaignStatus.FAILED: "failed",
        }

        if status in invalid_statuses:
            raise EosCampaignExecutionError(
                f"Cannot start campaign '{self._campaign_name}' as it already exists and is "
                f"'{invalid_statuses[status]}'. Please create a new campaign or re-submit "
                f"with 'resume=True'."
            )

    async def _resume_campaign(self, db: AsyncDbSession) -> None:
        """Resume an existing campaign by restoring its state."""
        await self._campaign_manager.update_campaign_submission(db, self._campaign_submission)

        await self._campaign_manager.delete_non_completed_campaign_protocol_runs(db, self._campaign_name)
        await self._sync_protocol_runs_completed_counter(db)

        if self._campaign_submission.optimize:
            self._optimizer_state = OptimizerState.NEEDS_RESTORATION

        log.info(f"Campaign '{self._campaign_name}' resumed")

    async def _sync_protocol_runs_completed_counter(self, db: AsyncDbSession) -> None:
        """Sync protocol_runs_completed counter with the actual count of completed protocol runs."""
        completed_count = len(
            await self._campaign_manager.get_campaign_protocol_run_names(
                db, self._campaign_name, status=ProtocolRunStatus.COMPLETED
            )
        )

        campaign = await self._campaign_manager.get_campaign(db, self._campaign_name)
        if campaign and completed_count != campaign.protocol_runs_completed:
            await self._campaign_manager.set_protocol_runs_completed(db, self._campaign_name, completed_count)

    async def _get_next_protocol_run_number(self, db: AsyncDbSession) -> int:
        """Get the next protocol run number (max existing + 1), handling gaps from cancelled runs."""
        all_protocol_run_names = await self._campaign_manager.get_campaign_protocol_run_names(db, self._campaign_name)

        # Also account for names reserved by pending (unresolved) samples
        for pending in self._pending_samples:
            all_protocol_run_names.extend(name for name, _ in pending.protocol_runs)

        max_run_num = 0
        prefix = f"{self._campaign_name}_run_"
        for name in all_protocol_run_names:
            if name.startswith(prefix):
                try:
                    run_num = int(name[len(prefix) :])
                    max_run_num = max(max_run_num, run_num)
                except ValueError:
                    pass

        return max_run_num + 1

    async def _initialize_optimizer(self) -> None:
        """Initialize the campaign optimizer if not already initialized."""
        if self._optimizer:
            return

        # Extract overrides from campaign submission meta
        optimizer_overrides = None
        if self._campaign_submission.meta:
            optimizer_overrides = self._campaign_submission.meta.get("optimizer_overrides")

        is_resume = self._optimizer_state == OptimizerState.NEEDS_RESTORATION

        log.info(f"Creating optimizer for campaign '{self._campaign_name}'...")
        (
            self._optimizer,
            optimizer_type_name,
            config_snapshot,
        ) = await self._campaign_optimizer_manager.create_campaign_optimizer_actor(
            self._protocol,
            self._campaign_name,
            self._campaign_submission.optimizer_ip,
            optimizer_overrides=optimizer_overrides,
            is_resume=is_resume,
            global_parameters=self._campaign_submission.global_parameters,
            protocol_run_parameters=self._campaign_submission.protocol_run_parameters,
        )

        # Persist optimizer config to campaign meta
        optimizer_config = {
            "optimizer_type": optimizer_type_name,
            "constructor_args": config_snapshot,
            "created_at": datetime.now(UTC).isoformat(),
        }
        async with self._db_interface.get_async_session() as db:
            await self._campaign_manager.update_campaign_meta(
                db, self._campaign_name, "beacon", {"optimizer_config": optimizer_config}
            )

        (
            self._optimizer_input_names,
            self._optimizer_output_names,
            self._optimizer_additional_parameters,
        ) = await self._campaign_optimizer_manager.get_input_and_output_names(self._campaign_name)

    async def _ensure_optimizer_initialized(self, db: AsyncDbSession) -> None:
        """Initialize the optimizer and restore state if needed."""
        if self._optimizer_state == OptimizerState.READY:
            return

        await self._initialize_optimizer()

        if self._optimizer_state == OptimizerState.NEEDS_RESTORATION:
            await self._restore_optimizer_state(db)

        self._optimizer_state = OptimizerState.READY

    async def progress_campaign(self) -> bool:
        """Progress the campaign by one cycle. Returns True if the campaign is completed."""
        try:
            if self._campaign_status != CampaignStatus.RUNNING:
                return self._campaign_status == CampaignStatus.CANCELLED

            if self._pending_pareto is not None:
                if self._pending_pareto.done():
                    await self._finalize_pareto()
                    return True
                return False

            await self._process_protocol_run_cancellations()
            await self._progress_protocol_runs()

            async with self._db_interface.get_async_session() as db:
                campaign = await self._campaign_manager.get_campaign(db, self._campaign_name)
                if not campaign:
                    raise EosCampaignExecutionError(f"Campaign '{self._campaign_name}' not found in database")

                if self._is_campaign_completed(campaign):
                    return await self._complete_campaign(db)

                await self._create_protocol_runs(db, campaign)
                return False

        except Exception as e:
            await self._handle_campaign_failure(e)
            raise

    async def _progress_protocol_runs(self) -> None:
        """Progress all running protocol runs and process completed ones."""
        async with self._db_interface.get_async_session() as db:
            completed_protocol_runs = []
            for run_name, executor in self._protocol_executors.items():
                complete = await executor.progress_protocol_run(db)
                if complete:
                    completed_protocol_runs.append(run_name)

            if completed_protocol_runs and self._campaign_submission.optimize:
                await self._process_results_for_optimization(db, completed_protocol_runs)

            for _ in completed_protocol_runs:
                await self._campaign_manager.increment_iteration(db, self._campaign_name)

        # Non-blocking: resolve report if done, flush queued reports if actor is free
        await self._try_resolve_pending_report()
        await self._try_flush_reports()

        for run_name in completed_protocol_runs:
            del self._protocol_executors[run_name]

    async def cancel_campaign(self) -> None:
        """Cancel the campaign and all running protocols."""
        async with self._db_interface.get_async_session() as db:
            campaign = await self._campaign_manager.get_campaign(db, self._campaign_name)
            if not campaign or campaign.status != CampaignStatus.RUNNING:
                raise EosCampaignExecutionError(
                    f"Cannot cancel campaign '{self._campaign_name}' with status "
                    f"'{campaign.status if campaign else 'None'}'. It must be running."
                )

            log.warning(f"Cancelling campaign '{self._campaign_name}'...")
            await self._campaign_manager.cancel_campaign(db, self._campaign_name)
            self._campaign_status = CampaignStatus.CANCELLED

            pending_protocol_run_names = [
                protocol_run_name for pending in self._pending_samples for protocol_run_name, _ in pending.protocol_runs
            ]
            if pending_protocol_run_names:
                await self._protocol_run_manager.cancel_protocol_runs_batch(db, pending_protocol_run_names)

        await self._cancel_running_protocol_runs()

        self._protocol_executors.clear()

        log.warning(f"Cancelled campaign '{self._campaign_name}'")

    async def _cancel_running_protocol_runs(self) -> None:
        """Cancel all running protocol runs sequentially with individual timeouts."""
        failed_cancellations = []

        for run_name, executor in self._protocol_executors.items():
            try:
                await asyncio.wait_for(executor.cancel_protocol_run(), timeout=15)
            except TimeoutError:
                failed_cancellations.append((run_name, "timeout"))
                log.warning(f"CMP '{self._campaign_name}' - Timeout while cancelling protocol run '{run_name}'")
            except EosProtocolRunCancellationError as e:
                failed_cancellations.append((run_name, str(e)))
                log.warning(f"CMP '{self._campaign_name}' - Error cancelling protocol run '{run_name}': {e}")

        if failed_cancellations:
            failed_details = "\n".join(f"- {run_name}: {reason}" for run_name, reason in failed_cancellations)
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_name}' - Failed to cancel {len(failed_cancellations)} "
                f"protocols:\n{failed_details}"
            )

    def queue_protocol_run_cancellation(self, protocol_run_name: str) -> bool:
        """Queue a protocol run for cancellation during the next progress cycle."""
        if protocol_run_name not in self._protocol_executors:
            return False

        self._pending_protocol_run_cancellations.add(protocol_run_name)
        log.info(f"CMP '{self._campaign_name}' - Queued protocol run '{protocol_run_name}' for cancellation")
        return True

    async def _process_protocol_run_cancellations(self) -> None:
        """Process any pending protocol run cancellations."""
        if not self._pending_protocol_run_cancellations:
            return

        to_cancel = list(self._pending_protocol_run_cancellations)
        self._pending_protocol_run_cancellations.clear()

        for protocol_run_name in to_cancel:
            if protocol_run_name not in self._protocol_executors:
                continue

            executor = self._protocol_executors[protocol_run_name]
            try:
                await asyncio.wait_for(executor.cancel_protocol_run(), timeout=15)
                del self._protocol_executors[protocol_run_name]
                log.warning(f"CMP '{self._campaign_name}' - Cancelled protocol run '{protocol_run_name}'")
            except TimeoutError:
                log.warning(
                    f"CMP '{self._campaign_name}' - Timeout while cancelling protocol run '{protocol_run_name}'"
                )
            except EosProtocolRunCancellationError as e:
                log.warning(f"CMP '{self._campaign_name}' - Error cancelling protocol run '{protocol_run_name}': {e}")
            except Exception as e:
                log.error(
                    f"CMP '{self._campaign_name}' - Unexpected error cancelling protocol run '{protocol_run_name}': {e}"
                )

    def cleanup(self) -> None:
        """Clean up resources when campaign executor is no longer needed."""
        self._cancel_pending_futures()
        if self._campaign_submission.optimize:
            self._campaign_optimizer_manager.terminate_campaign_optimizer_actor(self._campaign_name)

    async def _create_protocol_runs(self, db: AsyncDbSession, campaign: Campaign) -> None:
        """Create new protocol runs up to the maximum allowed concurrent runs."""
        # Resolve any completed samples — protocol runs already exist as CREATED
        still_pending = []
        for pending in self._pending_samples:
            if pending.future.done():
                resolved = await self._resolve_pending_sample(pending)
                for protocol_run_name, parameters in resolved:
                    await self._protocol_run_manager.update_protocol_run_parameters(db, protocol_run_name, parameters)
                    await self._create_single_protocol_run(db, protocol_run_name, parameters)
            else:
                still_pending.append(pending)
        self._pending_samples = still_pending

        # Account for protocol runs waiting in pending samples
        pending_slots = sum(len(p.protocol_runs) for p in self._pending_samples)
        effective_in_flight = len(self._protocol_executors) + pending_slots

        if not self._can_create_more_protocol_runs_with(campaign, effective_in_flight):
            return

        next_run_num = await self._get_next_protocol_run_number(db)

        while self._can_create_more_protocol_runs_with(campaign, effective_in_flight):
            protocol_run_name = f"{self._campaign_name}_run_{next_run_num}"
            next_run_num += 1
            iteration = campaign.protocol_runs_completed + effective_in_flight

            parameters = self._get_protocol_run_parameters(iteration)
            if parameters is not None:
                await self._create_single_protocol_run(db, protocol_run_name, parameters)
                effective_in_flight += 1
                continue

            # Batch all remaining slots into one optimizer sample(N) call
            batch: list[tuple[str, dict]] = [(protocol_run_name, self._get_base_params())]
            projected = effective_in_flight + 1
            while self._can_create_more_protocol_runs_with(campaign, projected):
                protocol_run_name = f"{self._campaign_name}_run_{next_run_num}"
                next_run_num += 1
                batch.append((protocol_run_name, self._get_base_params()))
                projected += 1
            await self._launch_batch_sample(db, batch)
            effective_in_flight = projected
            return

    async def _create_single_protocol_run(
        self, db: AsyncDbSession, protocol_run_name: str, parameters: dict[str, Any]
    ) -> None:
        """Create and start a single protocol run."""
        protocol_run_submission = ProtocolRunSubmission(
            name=protocol_run_name,
            type=self._protocol,
            owner=self._campaign_submission.owner,
            priority=self._campaign_submission.priority,
            parameters=parameters,
        )

        protocol_executor = self._protocol_executor_factory.create(
            protocol_run_submission, campaign=self._campaign_name
        )
        self._protocol_executors[protocol_run_name] = protocol_executor
        await protocol_executor.start_protocol_run(db)

    def _can_create_more_protocol_runs_with(self, campaign: Campaign, num_in_flight: int) -> bool:
        """Check if more protocols can be created given a projected in-flight count."""
        max_concurrent = self._campaign_submission.max_concurrent_protocol_runs
        max_total = self._campaign_submission.max_protocol_runs
        current_total = campaign.protocol_runs_completed + num_in_flight

        return num_in_flight < max_concurrent and (max_total == 0 or current_total < max_total)

    def _get_protocol_run_parameters(self, iteration: int) -> dict[str, Any] | None:
        """Get static parameters for a protocol run, or None if the optimizer should be used."""
        base_params = self._get_base_params()

        run_params = None
        if self._campaign_submission.protocol_run_parameters and iteration < len(
            self._campaign_submission.protocol_run_parameters
        ):
            run_params = self._campaign_submission.protocol_run_parameters[iteration]
        elif self._campaign_submission.optimize:
            return None
        elif not base_params:
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_name}' - No parameters provided for iteration {iteration}"
            )

        _merge_protocol_run_params(base_params, run_params)
        return base_params

    def _get_base_params(self) -> dict[str, Any]:
        """Get a deep copy of global parameters as the base for a protocol run."""
        return (
            copy.deepcopy(self._campaign_submission.global_parameters)
            if self._campaign_submission.global_parameters
            else {}
        )

    async def _launch_batch_sample(self, db: AsyncDbSession, batch: list[tuple[str, dict]]) -> None:
        """Launch a non-blocking batch optimizer sample for multiple protocols."""
        await self._ensure_optimizer_initialized(db)

        # Create protocol run records as CREATED before parameters are available
        for protocol_run_name, base_params in batch:
            submission = ProtocolRunSubmission(
                name=protocol_run_name,
                type=self._protocol,
                owner=self._campaign_submission.owner,
                priority=self._campaign_submission.priority,
                parameters=base_params,
            )
            await self._protocol_run_manager.create_protocol_run(db, submission, campaign=self._campaign_name)

        num = len(batch)
        run_names = ", ".join(name for name, _ in batch)
        log.info(f"CMP '{self._campaign_name}' - Sampling parameters for {num} protocol run(s): {run_names}")
        future = asyncio.create_task(_await_ray_ref(self._optimizer.sample_and_get_meta.remote(num)))
        self._pending_samples.append(_PendingOptimizerSample(future=future, protocol_runs=batch))

    async def _resolve_pending_sample(self, pending: _PendingOptimizerSample) -> list[tuple[str, dict[str, Any]]]:
        """Resolve a completed batch sample into (protocol_run_name, merged_params) pairs."""
        try:
            samples_df, meta = pending.future.result()
            if meta:
                await self._save_optimizer_meta_dict(meta)
            records = samples_df.to_dict(orient="records")
            log.debug(f"CMP '{self._campaign_name}' - Sampled parameters: {records}")
        except Exception as e:
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_name}' - Error sampling parameters from optimizer"
            ) from e

        result = []
        for (protocol_run_name, base_params), record in zip(pending.protocol_runs, records, strict=True):
            run_params = dict_utils.unflatten_dict(record)
            _merge_protocol_run_params(base_params, run_params)
            result.append((protocol_run_name, base_params))
        return result

    def _is_campaign_completed(self, campaign: Campaign) -> bool:
        """Check if campaign has completed all protocol runs."""
        max_protocol_runs = self._campaign_submission.max_protocol_runs
        return (
            0 < max_protocol_runs <= campaign.protocol_runs_completed
            and not self._protocol_executors
            and not self._pending_samples
        )

    async def _complete_campaign(self, db: AsyncDbSession) -> bool:
        """Complete the campaign. Returns False if waiting for async pareto computation."""
        if self._campaign_submission.optimize:
            # Flush any remaining queued reports before Pareto computation
            if self._queued_reports:
                await self._try_resolve_pending_report()
                if self._pending_report is not None:
                    return False  # Actor still busy, try next cycle
                await self._try_flush_reports()
            if not await self._wait_for_pending_report():
                return False

            await self._ensure_optimizer_initialized(db)
            log.info(f"Computing Pareto solutions for campaign '{self._campaign_name}'...")
            self._pending_pareto = asyncio.create_task(_await_ray_ref(self._optimizer.get_optimal_solutions.remote()))
            return False

        await self._campaign_manager.complete_campaign(db, self._campaign_name)
        return True

    async def _finalize_pareto(self) -> None:
        """Finalize campaign after pareto computation completes."""
        try:
            pareto_solutions_df = self._pending_pareto.result()
            pareto_solutions = pareto_solutions_df.to_dict(orient="records")
            async with self._db_interface.get_async_session() as db:
                await self._campaign_manager.set_pareto_solutions(db, self._campaign_name, pareto_solutions)
                await self._campaign_manager.complete_campaign(db, self._campaign_name)
        except Exception as e:
            raise EosCampaignExecutionError(f"CMP '{self._campaign_name}' - Error computing Pareto solutions") from e
        finally:
            self._pending_pareto = None

    async def _handle_campaign_failure(self, error: Exception) -> None:
        """Mark campaign as failed, cancel running protocols, and raise."""
        async with self._db_interface.get_async_session() as db:
            pending_protocol_run_names = [
                protocol_run_name for pending in self._pending_samples for protocol_run_name, _ in pending.protocol_runs
            ]
            if pending_protocol_run_names:
                try:
                    await self._protocol_run_manager.cancel_protocol_runs_batch(db, pending_protocol_run_names)
                except Exception:
                    log.warning(f"CMP '{self._campaign_name}' - Failed to cancel pending protocols")
            await self._campaign_manager.fail_campaign(db, self._campaign_name, error_message=str(error))

        self._cancel_pending_futures()
        self._campaign_status = CampaignStatus.FAILED

        try:
            await self._cancel_running_protocol_runs()
        except Exception:
            log.warning(
                f"CMP '{self._campaign_name}' - Errors occurred while cancelling running protocol runs after failure."
            )
        finally:
            self._protocol_executors.clear()

        raise EosCampaignExecutionError(f"Error executing campaign '{self._campaign_name}'") from error

    def _cancel_pending_futures(self) -> None:
        """Cancel any pending optimizer futures."""
        for pending in self._pending_samples:
            if not pending.future.done():
                pending.future.cancel()
        self._pending_samples.clear()
        for task in (self._pending_report, self._pending_pareto):
            if task is not None and not task.done():
                task.cancel()
        self._pending_report = None
        self._pending_pareto = None

    async def _restore_optimizer_state(self, db: AsyncDbSession) -> None:
        """Restore the optimizer state by reporting all completed protocol run results."""
        completed_protocol_run_names = await self._campaign_manager.get_campaign_protocol_run_names(
            db, self._campaign_name, status=ProtocolRunStatus.COMPLETED
        )

        inputs_df, outputs_df, additional = await self._collect_protocol_run_results(db, completed_protocol_run_names)

        # Piggyback additional params onto outputs_df for optimizer (BeaconOptimizer strips them)
        report_df = pd.concat([outputs_df, pd.DataFrame(additional)], axis=1) if additional else outputs_df
        await self._optimizer.report.remote(inputs_df, report_df)

        meta = await self._campaign_manager.get_campaign_meta(db, self._campaign_name)
        if meta and meta.get("beacon"):
            await self._optimizer.restore_optimizer_meta.remote(meta["beacon"])
            log.info(f"CMP '{self._campaign_name}' - Restored optimizer meta")

        log.info(
            f"CMP '{self._campaign_name}' - Restored optimizer state from {len(completed_protocol_run_names)} "
            f"completed protocols."
        )

    async def _collect_protocol_run_results(
        self, db: AsyncDbSession, protocol_run_names: list[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list]]:
        """Collect optimizer input/output/additional parameter values from completed protocol runs."""
        inputs = {input_name: [] for input_name in self._optimizer_input_names}
        outputs = {output_name: [] for output_name in self._optimizer_output_names}
        additional = {key: [] for key in self._optimizer_additional_parameters}

        # Collect all unique task names referenced by optimizer params
        all_param_refs = (
            self._optimizer_input_names + self._optimizer_output_names + self._optimizer_additional_parameters
        )
        task_names = list({ref.split(".")[0] for ref in all_param_refs})

        # Single batch query instead of N+1 individual queries
        task_lookup = await self._task_manager.get_tasks_by_protocol_runs(db, protocol_run_names, task_names)

        for protocol_run_name in protocol_run_names:
            for input_name in self._optimizer_input_names:
                reference_task_name, parameter_name = input_name.split(".")
                task = task_lookup.get((protocol_run_name, reference_task_name))
                inputs[input_name].append(task.input_parameters[parameter_name] if task else None)
            for output_name in self._optimizer_output_names:
                reference_task_name, parameter_name = output_name.split(".")
                task = task_lookup.get((protocol_run_name, reference_task_name))
                outputs[output_name].append(task.output_parameters[parameter_name] if task else None)
            for key in self._optimizer_additional_parameters:
                reference_task_name, parameter_name = key.split(".")
                task = task_lookup.get((protocol_run_name, reference_task_name))
                additional[key].append(task.output_parameters[parameter_name] if task else None)

        return pd.DataFrame(inputs), pd.DataFrame(outputs), additional

    async def _save_optimizer_meta_dict(self, meta: dict[str, Any]) -> None:
        """
        Save pre-fetched optimizer meta (journal, insights) to Campaign.meta.

        Merges into the existing 'beacon' key so optimizer_config is preserved.
        """
        async with self._db_interface.get_async_session() as db:
            current_meta = await self._campaign_manager.get_campaign_meta(db, self._campaign_name) or {}
            current_beacon = current_meta.get("beacon", {}) or {}
            merged_beacon = {**current_beacon, **meta}
            await self._campaign_manager.update_campaign_meta(db, self._campaign_name, "beacon", merged_beacon)

    async def _process_results_for_optimization(self, db: AsyncDbSession, completed_protocol_runs: list[str]) -> None:
        """Record protocol run results and queue an optimizer report (non-blocking)."""
        await self._ensure_optimizer_initialized(db)
        inputs_df, outputs_df, additional = await self._collect_protocol_run_results(db, completed_protocol_runs)

        # Store additional params under beacon key in sample meta
        meta_list = None
        if additional:
            meta_list = [
                {"beacon": {"additional_parameters": dict(zip(additional.keys(), vals, strict=True))}}
                for vals in zip(*additional.values(), strict=True)
            ]

        await self._campaign_optimizer_manager.record_campaign_samples(
            db, self._campaign_name, completed_protocol_runs, inputs_df, outputs_df, meta_list=meta_list
        )

        # Queue results for reporting — flushed when actor is free
        report_df = pd.concat([outputs_df, pd.DataFrame(additional)], axis=1) if additional else outputs_df
        self._queued_reports.append((inputs_df, report_df))

    async def _try_flush_reports(self) -> None:
        """Non-blocking: submit queued reports to optimizer if actor is free."""
        if not self._queued_reports:
            return

        # Resolve existing report first
        if self._pending_report is not None:
            if not self._pending_report.done():
                return  # Actor busy, try next cycle
            await self._resolve_report_result()

        # Merge all queued results into one report
        all_inputs = pd.concat([r[0] for r in self._queued_reports], ignore_index=True)
        all_reports = pd.concat([r[1] for r in self._queued_reports], ignore_index=True)
        self._queued_reports.clear()

        self._pending_report = asyncio.create_task(
            _await_ray_ref(self._optimizer.report_and_get_meta.remote(all_inputs, all_reports))
        )

    async def _try_resolve_pending_report(self) -> None:
        """Non-blocking: resolve pending report if done, skip if actor is still busy."""
        if self._pending_report is None or not self._pending_report.done():
            return
        await self._resolve_report_result()

    async def _resolve_report_result(self) -> None:
        """Extract meta from completed report and save it."""
        try:
            meta = self._pending_report.result()
            if meta:
                await self._save_optimizer_meta_dict(meta)
        except Exception as e:
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_name}' - Error reporting results to optimizer"
            ) from e
        finally:
            self._pending_report = None

    async def _wait_for_pending_report(self) -> bool:
        """Return True if no report is pending or it completed. False if still in progress."""
        if self._pending_report is None:
            return True
        if not self._pending_report.done():
            return False
        await self._resolve_report_result()
        return True

    @property
    def optimizer(self) -> ActorHandle | None:
        """Get the campaign optimizer actor handle."""
        return self._optimizer

    @property
    def campaign_submission(self) -> CampaignSubmission:
        """Get the campaign submission."""
        return self._campaign_submission
