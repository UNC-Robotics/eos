import asyncio
import time

from eos.configuration.protocol_graph import ProtocolGraph
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling.cpsat_scheduling_solver import CpSatSchedulingSolver
from eos.scheduling.exceptions import EosSchedulerError
from tests.fixtures import *

PROTOCOL = "run_if"


@pytest.mark.parametrize("setup_lab_protocol", [("multiplication_lab", PROTOCOL)], indirect=True)
class TestCpSatBackgroundSolve:
    @pytest.fixture
    def slow_solve(self, monkeypatch):
        original_solve = CpSatSchedulingSolver.solve

        def solve(solver, hint=None):
            solver._stopped.wait(1)  # Ends early on stop, like a running search
            return original_solve(solver, hint)

        monkeypatch.setattr(CpSatSchedulingSolver, "solve", solve)

    async def _register_runs(self, db, scheduler, protocol_run_manager, configuration_manager, names):
        for name in names:
            await protocol_run_manager.create_protocol_run(
                db, ProtocolRunSubmission(name=name, type=PROTOCOL, owner="test", parameters={"prep": {"number": 5}})
            )
            await protocol_run_manager.start_protocol_run(db, name)
            await scheduler.register_protocol_run(
                name, PROTOCOL, ProtocolGraph(configuration_manager.protocols[PROTOCOL])
            )

    async def test_solve_does_not_block_other_scheduler_calls(
        self, db, cpsat_scheduler, protocol_run_manager, configuration_manager, slow_solve
    ):
        names = ["bg_1", "bg_2"]
        await self._register_runs(db, cpsat_scheduler, protocol_run_manager, configuration_manager, names)

        version = cpsat_scheduler.state_version
        start = time.monotonic()
        assert await cpsat_scheduler.request_tasks(db, "bg_1") == []  # Solve started in the background
        await cpsat_scheduler.release_task(db, "prep", "bg_2")
        assert await cpsat_scheduler.request_tasks(db, "bg_2") == []
        assert time.monotonic() - start < 0.5

        scheduled = []
        while not scheduled and time.monotonic() - start < 10:
            await asyncio.sleep(0.05)
            for name in names:
                scheduled += await cpsat_scheduler.request_tasks(db, name)
        assert [task.name for task in scheduled] == ["prep"]
        assert cpsat_scheduler.state_version > version  # Finished solves wake waiting runs

    async def test_runs_unregistered_during_a_solve_are_dropped(
        self, db, cpsat_scheduler, protocol_run_manager, configuration_manager, slow_solve
    ):
        await self._register_runs(db, cpsat_scheduler, protocol_run_manager, configuration_manager, ["keep", "drop"])
        await cpsat_scheduler.request_tasks(db, "keep")
        await cpsat_scheduler.unregister_protocol_run(db, "drop")

        await asyncio.wait_for(asyncio.shield(cpsat_scheduler._pending_solve[0]), timeout=10)
        await cpsat_scheduler.request_tasks(db, "keep")
        assert set(cpsat_scheduler._schedule) == {"keep"}
        assert set(cpsat_scheduler._task_durations) == {"keep"}

    async def test_solve_is_stopped_when_no_runs_remain(
        self, db, cpsat_scheduler, protocol_run_manager, configuration_manager, slow_solve
    ):
        await self._register_runs(db, cpsat_scheduler, protocol_run_manager, configuration_manager, ["only"])
        await cpsat_scheduler.request_tasks(db, "only")
        future = cpsat_scheduler._pending_solve[0]

        start = time.monotonic()
        await cpsat_scheduler.unregister_protocol_run(db, "only")
        assert cpsat_scheduler._pending_solve is None
        with pytest.raises(EosSchedulerError, match="stopped"):
            await future  # Stopped before the search started, so it does not run to its time limit
        assert time.monotonic() - start < 0.5
