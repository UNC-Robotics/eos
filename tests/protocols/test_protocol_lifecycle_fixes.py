import asyncio

from eos.configuration.entities.task_def import DeviceAssignmentDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.orchestration.services.protocol_service import ProtocolService
from eos.orchestration.services.task_service import TaskService
from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRunSubmission
from eos.protocols.exceptions import EosProtocolRunExecutionError
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskStatus, TaskSubmission
from eos.tasks.exceptions import EosTaskCancellationError, EosTaskExecutionError
from tests.fixtures import *

LAB = "multiplication_lab"
PROTOCOL = "run_if"
MULTIPLIER = {"multiplier": DeviceAssignmentDef(lab_name=LAB, name="multiplier")}


class _RecordingTaskExecutor:
    """Starts nothing and records cancellations."""

    def __init__(self, events: list[str]):
        self.events = events

    async def request_task_execution(self, task_submission, scheduled_task):
        await asyncio.Event().wait()

    async def cancel_task(self, protocol_run_name, task_name):
        self.events.append(f"cancel {task_name}")


async def test_duplicate_and_stale_cancellation_requests_are_ignored():
    events: list[str] = []

    class _Executor:
        async def cancel_protocol_run(self):
            events.append("cancel")

    service = ProtocolService.__new__(ProtocolService)
    service._protocol_run_cancellation_queue = asyncio.Queue()
    service._submitted_protocol_runs = {"run": _Executor()}
    for name in ("run", "run", "finished_meanwhile"):
        await service._protocol_run_cancellation_queue.put(name)

    await service.process_protocol_run_cancellations()
    assert events == ["cancel"]
    assert service._submitted_protocol_runs == {}


@pytest.mark.parametrize("setup_lab_protocol", [(LAB, PROTOCOL)], indirect=True)
class TestProtocolLifecycleFixes:
    @pytest.fixture
    def make_executor(self, configuration_manager, protocol_run_manager, task_manager, greedy_scheduler, db_interface):
        def make(name: str, task_executor) -> ProtocolExecutor:
            return ProtocolExecutor(
                protocol_run_submission=ProtocolRunSubmission(
                    name=name, type=PROTOCOL, owner="test", parameters={"prep": {"number": 5}}
                ),
                protocol_graph=ProtocolGraph(configuration_manager.protocols[PROTOCOL]),
                protocol_run_manager=protocol_run_manager,
                task_manager=task_manager,
                task_executor=task_executor,
                scheduler=greedy_scheduler,
                db_interface=db_interface,
            )

        return make

    @pytest.mark.parametrize("outcome", ["cancellation_error", "cancelled"])
    async def test_a_cancelled_task_fails_its_run_instead_of_escaping(
        self, db, make_executor, protocol_run_manager, outcome
    ):
        executor = make_executor("cancel_escape", _RecordingTaskExecutor([]))
        await executor.start_protocol_run(db)

        async def cancelled_task():
            if outcome == "cancelled":
                raise asyncio.CancelledError
            raise EosTaskCancellationError("cancelled")

        future = asyncio.create_task(cancelled_task())
        await asyncio.wait({future})
        executor._task_output_futures["prep"] = future
        executor._current_task_submissions["prep"] = TaskSubmission(name="prep", type="Multiplication")

        with pytest.raises(EosProtocolRunExecutionError):
            await executor.progress_protocol_run(db)
        assert (await protocol_run_manager.get_protocol_run(db, "cancel_escape")).status == ProtocolRunStatus.FAILED

    async def test_cancelling_a_task_before_it_starts_leaves_nothing_behind(self, task_executor):
        submission = TaskSubmission(name="early", type="Sleep", protocol_run_name=None, input_parameters={"time": 1})
        future = asyncio.create_task(
            task_executor.request_task_execution(
                submission, ScheduledTask(name="early", protocol_run_name=None, devices={}, resources={})
            )
        )
        await asyncio.sleep(0)

        await task_executor.cancel_task(None, "early")  # No DB row exists yet
        with pytest.raises(EosTaskCancellationError):
            await future
        assert not task_executor._pending_tasks
        assert not task_executor._task_futures

    async def test_a_run_that_fails_to_start_is_unregistered(
        self, db, make_executor, protocol_run_manager, greedy_scheduler, monkeypatch
    ):
        async def fail(*args):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(protocol_run_manager, "start_protocol_run", fail)
        executor = make_executor("start_fails", _RecordingTaskExecutor([]))
        with pytest.raises(EosProtocolRunExecutionError):
            await executor.start_protocol_run(db)
        assert "start_fails" not in greedy_scheduler._registered_protocol_runs

    async def test_cancelling_a_run_stops_tasks_before_releasing_devices(
        self, db, make_executor, greedy_scheduler, monkeypatch
    ):
        events: list[str] = []
        executor = make_executor("cancel_order", _RecordingTaskExecutor(events))
        await executor.start_protocol_run(db)
        await db.commit()
        await executor.progress_protocol_run(db)
        await db.commit()
        assert "prep" in executor._current_task_submissions

        unregister = greedy_scheduler.unregister_protocol_run

        async def recording_unregister(db, name):
            events.append("unregister")
            await unregister(db, name)

        monkeypatch.setattr(greedy_scheduler, "unregister_protocol_run", recording_unregister)
        await executor.cancel_protocol_run()
        assert events == ["cancel prep", "unregister"]

    async def test_a_scheduler_change_during_a_request_is_not_missed(
        self, db, make_executor, greedy_scheduler, monkeypatch
    ):
        executor = make_executor("wakeup", _RecordingTaskExecutor([]))
        await executor.start_protocol_run(db)
        requests = 0
        request_tasks = greedy_scheduler.request_tasks

        async def counting_request_tasks(db, name):
            nonlocal requests
            requests += 1
            if requests == 1:
                greedy_scheduler._state_version += 1  # E.g. a background plan finished meanwhile
            return await request_tasks(db, name)

        monkeypatch.setattr(greedy_scheduler, "request_tasks", counting_request_tasks)
        await executor._execute_tasks(db, force=True)
        await executor._execute_tasks(db, force=False)
        assert requests == 2

    async def test_a_failed_completion_marks_the_run_failed(
        self, db, make_executor, protocol_run_manager, greedy_scheduler, monkeypatch
    ):
        executor = make_executor("complete_fails", _RecordingTaskExecutor([]))
        await executor.start_protocol_run(db)

        async def completed(*args):
            return True

        async def fail(*args):
            raise RuntimeError("write failed")

        monkeypatch.setattr(greedy_scheduler, "is_protocol_run_completed", completed)
        monkeypatch.setattr(protocol_run_manager, "complete_protocol_run", fail)
        with pytest.raises(EosProtocolRunExecutionError):
            await executor.progress_protocol_run(db)
        assert (await protocol_run_manager.get_protocol_run(db, "complete_fails")).status == ProtocolRunStatus.FAILED

    async def test_queued_on_demand_tasks_reject_duplicates_and_record_timeouts(
        self,
        db,
        db_interface,
        configuration_manager,
        task_manager,
        task_executor,
        greedy_scheduler,
        allocation_manager,
    ):
        service = TaskService(configuration_manager, task_manager, task_executor, greedy_scheduler, db_interface)
        await allocation_manager.allocate_devices(db, [(LAB, "multiplier")], "scientist")

        def submission(timeout=600):
            return TaskSubmission(
                name="queued",
                type="Multiplication",
                devices=MULTIPLIER,
                input_parameters={"number": 2, "factor": 3},
                allocation_timeout=timeout,
            )

        await service.submit_task(db, submission(timeout=0))
        with pytest.raises(EosTaskExecutionError, match="duplicate"):
            await service.submit_task(db, submission())
        await db.commit()

        await asyncio.sleep(0.01)
        await service.process_pending_on_demand()
        async with db_interface.get_async_session() as session:
            task = await task_manager.get_task(session, None, "queued")
        assert task.status == TaskStatus.FAILED
        assert "Timed out" in task.error_message
