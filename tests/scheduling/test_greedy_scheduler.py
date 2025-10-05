from typing import NamedTuple

from eos.experiments.entities.experiment import ExperimentDefinition
from eos.allocation.entities.allocation_request import (
    AllocationRequestStatus,
    AllocationType,
)
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskDefinition
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
        # Register experiment
        await greedy_scheduler.register_experiment("exp1", "abstract_experiment", experiment_graph)
        assert "exp1" in greedy_scheduler._registered_experiments

        # Unregister experiment
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
        """Helper to create and start an experiment"""
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type="abstract_experiment", name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

    async def _complete_task(self, db, task_manager, task_name: str, experiment_name: str = "experiment_1"):
        """Helper to mark a task as completed"""
        await task_manager.create_task(db, TaskDefinition(name=task_name, type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, task_name)
        await task_manager.complete_task(db, experiment_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        """Helper to verify a scheduled task matches expectations"""
        assert task.name == expected.task_name
        device = next(iter(task.devices.values()))
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name
        assert task.allocations.status == AllocationRequestStatus.ALLOCATED

    async def _process_and_verify_tasks(
        self, db, scheduler, resource_manager, task_manager, experiment_name: str, expected_tasks: list[ExpectedTask]
    ):
        """Helper to process and verify a batch of scheduled tasks"""
        # Request initial scheduling (submits resource requests)
        await scheduler.request_tasks(db, experiment_name)
        # Process resource allocation
        await resource_manager.process_requests(db)
        # Get scheduled tasks
        tasks = await scheduler.request_tasks(db, experiment_name)

        # Verify results
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
        """Test complete experiment scheduling workflow"""
        # Setup experiment
        await self._create_and_start_experiment(db, experiment_manager)
        await greedy_scheduler.register_experiment("experiment_1", "abstract_experiment", experiment_graph)

        # Define expected task scheduling sequence
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

        # Process each batch of tasks
        for expected_batch in scheduling_sequence:
            await self._process_and_verify_tasks(
                db, greedy_scheduler, allocation_manager, task_manager, "experiment_1", expected_batch
            )

        # Verify experiment completion
        assert await greedy_scheduler.is_experiment_completed(db, "experiment_1")

        # Verify no more tasks are scheduled
        await greedy_scheduler.request_tasks(db, "experiment_1")
        await allocation_manager.process_requests(db)
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
        """Verify greedy scheduler allocates dynamic devices (allowed_devices)."""
        experiment_type = "dynamic_device_experiment"
        experiment_name = "dyn_exp_1"

        # Create and start experiment
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        # Register experiment
        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: Task A requires a DT3 device dynamically
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name

        task_a = tasks_by_name["A"]
        assert task_a.allocations.status == AllocationRequestStatus.ALLOCATED
        assert len(task_a.devices) == 1
        # Any DT3 device from the lab is acceptable
        device_a = next(iter(task_a.devices.values()))
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}
        assert device_a.lab_name == "dynamic_lab"

        # Complete A to release devices
        await task_manager.create_task(db, TaskDefinition(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B (DT2) and C (DT3 with allowed_devices=DX3B)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert task_b.allocations.status == AllocationRequestStatus.ALLOCATED
        assert len(task_b.devices) == 1
        device_b = next(iter(task_b.devices.values()))
        assert device_b.lab_name == "dynamic_lab"
        assert device_b.name in {"DY2A", "DY2B"}
        await task_manager.create_task(db, TaskDefinition(name="B", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        assert task_c.allocations.status == AllocationRequestStatus.ALLOCATED
        # C has allowed_devices constraint -> must be DX3B
        assert len(task_c.devices) == 1
        device_c = next(iter(task_c.devices.values()))
        assert device_c.name == "DX3B"
        assert device_c.lab_name == "dynamic_lab"
        await task_manager.create_task(db, TaskDefinition(name="C", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D (DT5)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name

        task_d = tasks_by_name["D"]
        assert task_d.allocations.status == AllocationRequestStatus.ALLOCATED
        assert len(task_d.devices) == 1
        device_d = next(iter(task_d.devices.values()))
        assert device_d.lab_name == "dynamic_lab"
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskDefinition(name="D", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Step 4: E (device reference to C.device_1)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name
        await task_manager.create_task(db, TaskDefinition(name="E", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "E")
        await task_manager.complete_task(db, experiment_name, "E")

        # Step 5: F (device reference to E.device_1)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name
        await task_manager.create_task(db, TaskDefinition(name="F", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "F")
        await task_manager.complete_task(db, experiment_name, "F")

        # Step 6: G (device references to A.device_1 and D.device_1)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name
        await task_manager.create_task(db, TaskDefinition(name="G", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "G")
        await task_manager.complete_task(db, experiment_name, "G")

        # Confirm experiment completion and no more tasks
        assert await greedy_scheduler.is_experiment_completed(db, experiment_name)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
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
        """Verify device references ensure same device is used across dependent tasks."""
        experiment_type = "dynamic_device_experiment"
        experiment_name = "dev_ref_exp_1"

        # Create and start experiment
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        # Register experiment
        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: Task A dynamically allocates a DT3 device
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name

        task_a = tasks_by_name["A"]
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}

        await task_manager.create_task(db, TaskDefinition(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B and C execute (C must get DX3B due to allowed_devices constraint)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        await task_manager.create_task(db, TaskDefinition(name="B", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        device_c = task_c.devices["device_1"]
        assert device_c.name == "DX3B"  # Constrained by allowed_devices
        await task_manager.create_task(db, TaskDefinition(name="C", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D executes
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name

        task_d = tasks_by_name["D"]
        device_d = task_d.devices["device_1"]
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskDefinition(name="D", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Step 4: E references C.device_1 - must use same device (DX3B)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name

        task_e = tasks_by_name["E"]
        device_e = task_e.devices["device_1"]
        assert device_e.name == device_c.name  # Must match C
        assert device_e.name == "DX3B"
        await task_manager.create_task(db, TaskDefinition(name="E", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "E")
        await task_manager.complete_task(db, experiment_name, "E")

        # Step 5: F references E.device_1 (depth-2 reference) - must use same device (DX3B)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name

        task_f = tasks_by_name["F"]
        device_f = task_f.devices["device_1"]
        assert device_f.name == device_e.name  # Must match E
        assert device_f.name == device_c.name  # Must match C (transitively)
        assert device_f.name == "DX3B"
        await task_manager.create_task(db, TaskDefinition(name="F", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "F")
        await task_manager.complete_task(db, experiment_name, "F")

        # Step 6: G references A.device_1 and D.device_1 - must use both devices
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name

        task_g = tasks_by_name["G"]
        assert len(task_g.devices) == 2
        device_g_analyzer = task_g.devices["analyzer"]
        device_g_processor = task_g.devices["processor"]
        assert device_g_analyzer.name == device_a.name  # Must match A
        assert device_g_processor.name == device_d.name  # Must match D
        await task_manager.create_task(db, TaskDefinition(name="G", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "G")
        await task_manager.complete_task(db, experiment_name, "G")

        # Verify experiment completion
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

        # Create and start experiment
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=experiment_type, name=experiment_name, owner="test")
        )
        await experiment_manager.start_experiment(db, experiment_name)

        # Register experiment
        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await greedy_scheduler.register_experiment(experiment_name, experiment_type, graph)

        def container_names(task: ScheduledTask) -> set[str]:
            return {a.name for a in task.allocations.allocations if a.allocation_type == AllocationType.RESOURCE}

        # Step 1: A requires dynamic beaker_500
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert task_a.allocations.status == AllocationRequestStatus.ALLOCATED
        names_a = container_names(task_a)
        assert len(names_a) == 1
        assert next(iter(names_a)) in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskDefinition(name="A", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B (dynamic beaker_500) and C (specific B500B)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert task_b.allocations.status == AllocationRequestStatus.ALLOCATED
        names_b = container_names(task_b)
        assert len(names_b) == 1
        assert next(iter(names_b)) in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskDefinition(name="B", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        assert task_c.allocations.status == AllocationRequestStatus.ALLOCATED
        names_c = container_names(task_c)
        assert len(names_c) == 1
        assert next(iter(names_c)) == "B500B"
        await task_manager.create_task(
            db, TaskDefinition(name="C", type="Container Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D (dynamic vial)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        tasks = await greedy_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        assert task_d.allocations.status == AllocationRequestStatus.ALLOCATED
        names_d = container_names(task_d)
        assert len(names_d) == 1
        assert next(iter(names_d)) in {"VIAL1", "VIAL2"}
        await task_manager.create_task(
            db, TaskDefinition(name="D", type="Container Vial Usage", experiment_name=experiment_name)
        )
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Confirm completion and no further tasks
        assert await greedy_scheduler.is_experiment_completed(db, experiment_name)
        await greedy_scheduler.request_tasks(db, experiment_name)
        await allocation_manager.process_requests(db)
        assert len(await greedy_scheduler.request_tasks(db, experiment_name)) == 0
