from typing import NamedTuple

from eos.experiments.entities.experiment import ExperimentSubmission
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *


class ExpectedTask(NamedTuple):
    """Helper class to define expected task scheduling results"""

    task_name: str
    lab_name: str
    device_name: str


@pytest.fixture()
def experiment_graph(configuration_manager):
    experiment = configuration_manager.experiments["abstract_experiment"]
    return ExperimentGraph(experiment)


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", "abstract_experiment")], indirect=True)
class TestGreedyScheduler:
    @pytest.mark.asyncio
    async def test_register_experiment(self, greedy_scheduler, experiment_graph):
        await greedy_scheduler.register_experiment("exp1", "abstract_experiment", experiment_graph)
        assert greedy_scheduler._registered_experiments["exp1"] == (
            "abstract_experiment",
            experiment_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_experiment(self, greedy_scheduler, experiment_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.register_experiment("exp1", "invalid_type", experiment_graph)

    @pytest.mark.asyncio
    async def test_unregister_experiment(self, db, greedy_scheduler, experiment_graph, setup_lab_experiment):
        await greedy_scheduler.register_experiment("exp1", "abstract_experiment", experiment_graph)
        assert "exp1" in greedy_scheduler._registered_experiments
        await greedy_scheduler.unregister_experiment(db, "exp1")
        assert "exp1" not in greedy_scheduler._registered_experiments

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_experiment(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.unregister_experiment(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_experiment(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_experiment(self, db, experiment_manager, experiment_name: str = "experiment_1"):
        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type="abstract_experiment", name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

    async def _complete_task(self, db, task_manager, task_name: str, experiment_name: str = "experiment_1"):
        await task_manager.create_task(db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, task_name)
        await task_manager.complete_task(db, experiment_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        assert task.name == expected.task_name
        device = next(iter(task.devices.values()))
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self, db, scheduler, task_manager, experiment_name: str, expected_tasks: list[ExpectedTask]
    ):
        tasks = await scheduler.request_tasks(db, experiment_name)

        assert len(tasks) == len(expected_tasks)
        for task, expected in zip(tasks, expected_tasks, strict=False):
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, experiment_name)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        greedy_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        await self._create_and_start_experiment(db, experiment_manager)
        await greedy_scheduler.register_experiment("experiment_1", "abstract_experiment", experiment_graph)

        scheduling_sequence = [
            [ExpectedTask("A", "abstract_lab", "D2")],
            [ExpectedTask("B", "abstract_lab", "D1"), ExpectedTask("C", "abstract_lab", "D3")],
            [
                ExpectedTask("D", "abstract_lab", "D1"),
                ExpectedTask("E", "abstract_lab", "D3"),
                ExpectedTask("F", "abstract_lab", "D2"),
            ],
            [ExpectedTask("G", "abstract_lab", "D5")],
            [ExpectedTask("H", "abstract_lab", "D6")],
        ]

        for expected_batch in scheduling_sequence:
            await self._process_and_verify_tasks(db, greedy_scheduler, task_manager, "experiment_1", expected_batch)

        assert await greedy_scheduler.is_experiment_completed(db, "experiment_1")

        final_tasks = await greedy_scheduler.request_tasks(db, "experiment_1")
        assert len(final_tasks) == 0


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_device_experiment")], indirect=True)
class TestGreedySchedulerDynamicDevices:
    @pytest.mark.asyncio
    async def test_dynamic_device_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        experiment_type = "dynamic_device_experiment"
        experiment_name = "dyn_exp_1"

        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: Task A requires a DT3 device dynamically
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.devices) == 1
        device_a = next(iter(task_a.devices.values()))
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}
        assert device_a.lab_name == "dynamic_lab"

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B (DT2) and C (DT3 with allowed_devices=DX3B)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.devices) == 1
        device_b = next(iter(task_b.devices.values()))
        assert device_b.lab_name == "dynamic_lab"
        assert device_b.name in {"DY2A", "DY2B"}
        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.devices) == 1
        device_c = next(iter(task_c.devices.values()))
        assert device_c.name == "DX3B"
        assert device_c.lab_name == "dynamic_lab"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Steps 3-6: D, E, F, G
        for task_name in ["D", "E", "F", "G"]:
            tasks = await greedy_scheduler.request_tasks(db, experiment_name)
            tasks_by_name = {t.name: t for t in tasks}
            assert task_name in tasks_by_name
            await task_manager.create_task(
                db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name)
            )
            await task_manager.start_task(db, experiment_name, task_name)
            await task_manager.complete_task(db, experiment_name, task_name)

        assert await greedy_scheduler.is_experiment_completed(db, experiment_name)
        assert len(await greedy_scheduler.request_tasks(db, experiment_name)) == 0


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_device_experiment")], indirect=True)
class TestGreedySchedulerDeviceReferences:
    @pytest.mark.asyncio
    async def test_device_reference_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        experiment_type = "dynamic_device_experiment"
        experiment_name = "dev_ref_exp_1"

        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: A dynamically allocates DT3
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B and C (C must get DX3B)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        device_c = task_c.devices["device_1"]
        assert device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        device_d = task_d.devices["device_1"]
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Step 4: E references C.device_1 -> DX3B
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name
        task_e = tasks_by_name["E"]
        device_e = task_e.devices["device_1"]
        assert device_e.name == device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="E", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "E")
        await task_manager.complete_task(db, experiment_name, "E")

        # Step 5: F references E.device_1 -> DX3B
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name
        task_f = tasks_by_name["F"]
        device_f = task_f.devices["device_1"]
        assert device_f.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="F", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "F")
        await task_manager.complete_task(db, experiment_name, "F")

        # Step 6: G references A.device_1 and D.device_1
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name
        task_g = tasks_by_name["G"]
        assert len(task_g.devices) == 2
        assert task_g.devices["analyzer"].name == device_a.name
        assert task_g.devices["processor"].name == device_d.name
        await task_manager.create_task(db, TaskSubmission(name="G", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "G")
        await task_manager.complete_task(db, experiment_name, "G")

        assert await greedy_scheduler.is_experiment_completed(db, experiment_name)


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_resource_experiment")], indirect=True)
class TestGreedySchedulerDynamicContainers:
    @pytest.mark.asyncio
    async def test_dynamic_container_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        experiment_type = "dynamic_resource_experiment"
        experiment_name = "dyn_cont_1"

        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: A requires dynamic beaker_500
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.resources) == 1
        res_a = next(iter(task_a.resources.values()))
        assert res_a in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskSubmission(name="A", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B (dynamic beaker_500) and C (specific B500B)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.resources) == 1
        res_b = next(iter(task_b.resources.values()))
        assert res_b in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskSubmission(name="B", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.resources) == 1
        res_c = next(iter(task_c.resources.values()))
        assert res_c == "B500B"
        await task_manager.create_task(
            db, TaskSubmission(name="C", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D (dynamic vial)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        assert len(task_d.resources) == 1
        res_d = next(iter(task_d.resources.values()))
        assert res_d in {"VIAL1", "VIAL2"}
        await task_manager.create_task(
            db, TaskSubmission(name="D", type="Container Vial Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        assert await greedy_scheduler.is_experiment_completed(db, experiment_name)
        assert len(await greedy_scheduler.request_tasks(db, experiment_name)) == 0
