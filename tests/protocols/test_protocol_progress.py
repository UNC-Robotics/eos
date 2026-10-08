import asyncio
import time

import eos.protocols.protocol_executor as protocol_executor_module
import eos.scheduling.cpsat_scheduler as cpsat_scheduler_module
import eos.scheduling.heuristic_scheduler as heuristic_scheduler_module
from eos.configuration.protocol_graph import ProtocolGraph
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.tasks.entities.task import TaskStatus
from tests.fixtures import *

PROTOCOL = "run_if"


class _LongRunningTaskExecutor:
    """Starts tasks in the DB and never completes them."""

    def __init__(self, task_manager, db_interface):
        self._task_manager, self._db_interface = task_manager, db_interface

    async def request_task_execution(self, task_submission, scheduled_task):
        async with self._db_interface.get_async_session() as db:
            await self._task_manager.create_task(db, task_submission)
            await self._task_manager.start_task(db, task_submission.protocol_run_name, task_submission.name)
        await asyncio.Event().wait()

    async def cancel_task(self, *args):
        pass


def _make_executor(
    name, number, scheduler, task_executor, configuration_manager, protocol_run_manager, task_manager, db_interface
):
    return ProtocolExecutor(
        protocol_run_submission=ProtocolRunSubmission(
            name=name, type=PROTOCOL, owner="test", parameters={"prep": {"number": number}}
        ),
        protocol_graph=ProtocolGraph(configuration_manager.protocols[PROTOCOL]),
        protocol_run_manager=protocol_run_manager,
        task_manager=task_manager,
        task_executor=task_executor,
        scheduler=scheduler,
        db_interface=db_interface,
    )


@pytest.mark.parametrize("setup_lab_protocol", [("multiplication_lab", PROTOCOL)], indirect=True)
@pytest.mark.parametrize("scheduler_name", ["greedy", "heuristic", "cpsat"])
class TestProtocolProgress:
    @pytest.fixture
    def scheduler(self, scheduler_name, greedy_scheduler, heuristic_scheduler, cpsat_scheduler):
        return {"greedy": greedy_scheduler, "heuristic": heuristic_scheduler, "cpsat": cpsat_scheduler}[scheduler_name]

    async def test_blocked_runs_do_no_db_work_until_something_changes(
        self,
        scheduler,
        db_interface,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        monkeypatch,
    ):
        task_executor = _LongRunningTaskExecutor(task_manager, db_interface)
        executors = [
            _make_executor(
                f"blocked_{i}",
                5,
                scheduler,
                task_executor,
                configuration_manager,
                protocol_run_manager,
                task_manager,
                db_interface,
            )
            for i in range(5)
        ]
        for executor in executors:
            async with db_interface.get_async_session() as db:
                await executor.start_protocol_run(db)

        async def spin():
            for executor in executors:
                async with db_interface.get_async_session() as db:
                    assert not await executor.progress_protocol_run(db)
            await asyncio.sleep(0.01)

        # Settle: one run's first task starts and the others wait for its device
        for _ in range(50):
            with count_statements(db_interface) as statements:
                await spin()
            if not statements and getattr(scheduler, "_pending_solve", None) is None:
                break

        with count_statements(db_interface) as statements:
            for _ in range(5):
                await spin()
        assert statements == []

        # Runs still re-poll the scheduler periodically
        monkeypatch.setattr(protocol_executor_module, "SCHEDULER_POLL_INTERVAL", 0)
        monkeypatch.setattr(heuristic_scheduler_module, "SCHEDULER_POLL_INTERVAL", 0)
        monkeypatch.setattr(cpsat_scheduler_module, "SCHEDULER_POLL_INTERVAL", 0)
        with count_statements(db_interface) as statements:
            await spin()
        assert statements

        for executor in executors:
            for future in executor._task_output_futures.values():
                future.cancel()

    @pytest.mark.slow
    async def test_concurrent_runs_never_start_skipped_tasks(
        self,
        scheduler,
        db_interface,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        task_executor,
    ):
        task_executor._scheduler = scheduler
        executors = {
            _make_executor(
                f"concurrent_{i}",
                [5, 50, -5][i % 3],
                scheduler,
                task_executor,
                configuration_manager,
                protocol_run_manager,
                task_manager,
                db_interface,
            ): None
            for i in range(6)
        }
        for executor in executors:
            async with db_interface.get_async_session() as db:
                await executor.start_protocol_run(db)

        deadline = time.monotonic() + 60
        while executors and time.monotonic() < deadline:
            await task_executor.process_tasks()
            for executor in list(executors):
                async with db_interface.get_async_session() as db:
                    if await executor.progress_protocol_run(db):
                        del executors[executor]
            await task_executor.process_new_tasks()
            await asyncio.sleep(0.05)
        assert not executors

        async with db_interface.get_async_session() as db:
            for i in range(6):
                assert (await task_manager.get_task(db, f"concurrent_{i}", "converge")).status == TaskStatus.COMPLETED
