"""End-to-end run_if coverage: execute the branching protocol and assert which tasks run vs. skip."""

import asyncio

from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.tasks.entities.task import TaskStatus
from tests.fixtures import *

LAB_NAME = "multiplication_lab"
PROTOCOL = "run_if"

C, S = TaskStatus.COMPLETED, TaskStatus.SKIPPED

# prep.number == prep.product (factor 1) steers the branch. converge fans in over
# high_prep, low_prep, and default_task, resolving to the single live branch.
# Each scenario gives a label, prep.number, expected task statuses, and converge's product.
SCENARIOS = [
    # high branch, big inner path: high_prep.product (200) > 100
    (
        "high_big",
        200,
        {
            "prep": C,
            "high_prep": C,
            "inner_big": C,
            "inner_small": S,
            "low_prep": S,
            "chain_small": S,
            "default_task": S,
            "converge": C,
        },
        200,
    ),
    # high branch, small inner path: 10 < 50 <= 100
    (
        "high_small",
        50,
        {
            "prep": C,
            "high_prep": C,
            "inner_big": S,
            "inner_small": C,
            "low_prep": S,
            "chain_small": S,
            "default_task": S,
            "converge": C,
        },
        50,
    ),
    # default branch: 0 <= 5 <= 10
    (
        "default",
        5,
        {
            "prep": C,
            "high_prep": S,
            "inner_big": S,
            "inner_small": S,
            "low_prep": S,
            "chain_small": S,
            "default_task": C,
            "converge": C,
        },
        9,
    ),
    # boundary: strict `>`, so 10 is not high; falls to default
    (
        "boundary",
        10,
        {
            "prep": C,
            "high_prep": S,
            "inner_big": S,
            "inner_small": S,
            "low_prep": S,
            "chain_small": S,
            "default_task": C,
            "converge": C,
        },
        9,
    ),
    # low branch: chain_small is non-conditional and runs because low_prep ran
    (
        "low",
        -5,
        {
            "prep": C,
            "high_prep": S,
            "inner_big": S,
            "inner_small": S,
            "low_prep": C,
            "chain_small": C,
            "default_task": S,
            "converge": C,
        },
        5,
    ),
]


@pytest.mark.parametrize("setup_lab_protocol", [(LAB_NAME, PROTOCOL)], indirect=True)
class TestRunIfBranching:
    @pytest.fixture
    def make_executor(
        self, protocol_run_manager, task_manager, task_executor, greedy_scheduler, protocol_graph, db_interface
    ):
        def _make(number: int, run_name: str) -> ProtocolExecutor:
            return ProtocolExecutor(
                protocol_run_submission=ProtocolRunSubmission(
                    name=run_name, type=PROTOCOL, owner="test", parameters={"prep": {"number": number}}
                ),
                protocol_graph=protocol_graph,
                protocol_run_manager=protocol_run_manager,
                task_manager=task_manager,
                task_executor=task_executor,
                scheduler=greedy_scheduler,
                db_interface=db_interface,
            )

        return _make

    @staticmethod
    async def _run_to_completion(executor, task_executor, db_interface):
        async with db_interface.get_async_session() as db:
            await executor.start_protocol_run(db)
        completed = False
        while not completed:
            async with db_interface.get_async_session() as db:
                completed = await executor.progress_protocol_run(db)
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

    @pytest.mark.parametrize(("label", "number", "expected_statuses", "converge_product"), SCENARIOS)
    async def test_branch_runs_and_skips(
        self,
        make_executor,
        task_executor,
        task_manager,
        db_interface,
        label,
        number,
        expected_statuses,
        converge_product,
    ):
        run_name = f"run_if_{label}"
        await self._run_to_completion(make_executor(number, run_name), task_executor, db_interface)

        async with db_interface.get_async_session() as db:
            for task_name, expected in expected_statuses.items():
                task = await task_manager.get_task(db, run_name, task_name)
                assert task is not None, f"task '{task_name}' was not recorded"
                assert task.status == expected, f"task '{task_name}': expected {expected}, got {task.status}"

            converge = await task_manager.get_task(db, run_name, "converge")
            assert converge.output_parameters["product"] == converge_product
