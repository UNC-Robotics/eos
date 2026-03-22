import copy
from typing import NamedTuple

from eos.experiments.entities.experiment import ExperimentSubmission
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *

EXPERIMENT_TYPE = "abstract_experiment_2"


class ExpectedTask(NamedTuple):
    """Helper class to define expected task scheduling results"""

    task_name: str
    lab_name: str
    device_name: str


@pytest.fixture()
def experiment_graph(configuration_manager):
    experiment = configuration_manager.experiments["abstract_experiment_2"]
    return ExperimentGraph(experiment)


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", EXPERIMENT_TYPE)], indirect=True)
class TestCpSatScheduler:
    @pytest.mark.asyncio
    async def test_register_experiment(self, cpsat_scheduler, experiment_graph):
        await cpsat_scheduler.register_experiment("exp1", EXPERIMENT_TYPE, experiment_graph)
        assert cpsat_scheduler._registered_experiments["exp1"] == (
            EXPERIMENT_TYPE,
            experiment_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_experiment(self, cpsat_scheduler, experiment_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.register_experiment("exp1", "invalid_type", experiment_graph)

    @pytest.mark.asyncio
    async def test_unregister_experiment(self, db, cpsat_scheduler, experiment_graph, setup_lab_experiment):
        # Register experiment
        await cpsat_scheduler.register_experiment("exp1", EXPERIMENT_TYPE, experiment_graph)
        assert "exp1" in cpsat_scheduler._registered_experiments

        # Unregister experiment
        await cpsat_scheduler.unregister_experiment(db, "exp1")
        assert "exp1" not in cpsat_scheduler._registered_experiments

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_experiment(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.unregister_experiment(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_experiment(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_experiment(
        self, db, experiment_manager, experiment_name: str = "experiment_1", priority: int = 0
    ):
        """Helper to create and start an experiment"""
        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=EXPERIMENT_TYPE, name=experiment_name, owner="test", priority=priority)
        )
        await experiment_manager.start_experiment(db, experiment_name)

    async def _complete_task(self, db, task_manager, task_name: str, experiment_name: str = "experiment_1"):
        """Helper to mark a task as completed"""
        await task_manager.create_task(db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, task_name)
        await task_manager.complete_task(db, experiment_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        """Helper to verify a scheduled task matches expectations"""
        assert task.name == expected.task_name
        device = task.devices["device_1"]
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self, db, scheduler, allocation_manager, task_manager, experiment_name: str, expected_tasks: list[ExpectedTask]
    ):
        """Helper to process and verify a batch of scheduled tasks (order not enforced)"""
        tasks = await scheduler.request_tasks(db, experiment_name)
        if not tasks:
            tasks = await scheduler.request_tasks(db, experiment_name)

        tasks_by_name = {task.name: task for task in tasks}

        # Verify each expected task exists and then complete it
        for expected in expected_tasks:
            task = tasks_by_name.get(expected.task_name)
            assert task is not None, f"Expected task with id {expected.task_name} not found"
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, experiment_name)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        """Test complete experiment scheduling workflow"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Setup experiment
        await self._create_and_start_experiment(db, experiment_manager)
        await cpsat_scheduler.register_experiment("experiment_1", EXPERIMENT_TYPE, experiment_graph)

        # Define expected task scheduling sequence
        scheduling_sequence = [
            [ExpectedTask("A", "abstract_lab", "D1")],
            [ExpectedTask("B", "abstract_lab", "D2"), ExpectedTask("C", "abstract_lab", "D3")],
            [ExpectedTask("D", "abstract_lab", "D3")],
            [ExpectedTask("E", "abstract_lab", "D4"), ExpectedTask("F", "abstract_lab", "D3")],
            [ExpectedTask("G", "abstract_lab", "D5")],
        ]

        # Process each batch of tasks
        for expected_batch in scheduling_sequence:
            await self._process_and_verify_tasks(
                db, cpsat_scheduler, allocation_manager, task_manager, "experiment_1", expected_batch
            )

        # Verify experiment completion
        assert await cpsat_scheduler.is_experiment_completed(db, "experiment_1")

        # Verify no more tasks are scheduled
        final_tasks = await cpsat_scheduler.request_tasks(db, "experiment_1")
        assert len(final_tasks) == 0


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_device_experiment")], indirect=True)
class TestCpSatSchedulerDynamicDevices:
    @pytest.mark.asyncio
    async def test_dynamic_device_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        """Verify CP-SAT schedules tasks with dynamic device allocation, respecting constraints."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Create and start experiment
        experiment_type = "dynamic_device_experiment"
        experiment_name = "dyn_exp_1"
        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test", priority=0)
        )
        await experiment_manager.start_experiment(db, experiment_name)

        # Register experiment
        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await cpsat_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: Task A requires a DT3 device dynamically
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, experiment_name)

        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.devices) == 1
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}
        assert device_a.lab_name == "dynamic_lab"

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B (DT2) and C (DT3 with allowed_devices=DX3B)
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.devices) == 1
        device_b = task_b.devices["device_1"]
        assert device_b.lab_name == "dynamic_lab"
        assert device_b.name in {"DY2A", "DY2B"}
        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "B")
        await task_manager.complete_task(db, experiment_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.devices) == 1
        device_c = task_c.devices["device_1"]
        assert device_c.name == "DX3B"
        assert device_c.lab_name == "dynamic_lab"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "C")
        await task_manager.complete_task(db, experiment_name, "C")

        # Step 3: D (DT5)
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        assert len(task_d.devices) == 1
        device_d = task_d.devices["device_1"]
        assert device_d.lab_name == "dynamic_lab"
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Steps 4-6: E, F, G
        for task_name in ["E", "F", "G"]:
            tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
            tasks_by_name = {t.name: t for t in tasks}
            assert task_name in tasks_by_name
            await task_manager.create_task(
                db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name)
            )
            await task_manager.start_task(db, experiment_name, task_name)
            await task_manager.complete_task(db, experiment_name, task_name)

        # Verify experiment completion
        assert await cpsat_scheduler.is_experiment_completed(db, experiment_name)
        assert len(await cpsat_scheduler.request_tasks(db, experiment_name)) == 0


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_device_experiment")], indirect=True)
class TestCpSatSchedulerDeviceReferences:
    @pytest.mark.asyncio
    async def test_device_reference_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        """Verify CP-SAT device references ensure same device is used across dependent tasks."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        experiment_type = "dynamic_device_experiment"
        experiment_name = "dev_ref_cpsat_exp_1"

        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test", priority=0)
        )
        await experiment_manager.start_experiment(db, experiment_name)

        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await cpsat_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: Task A dynamically allocates a DT3 device
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "A")
        await task_manager.complete_task(db, experiment_name, "A")

        # Step 2: B and C (C must get DX3B)
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
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
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        device_d = task_d.devices["device_1"]
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "D")
        await task_manager.complete_task(db, experiment_name, "D")

        # Step 4: E references C.device_1 - must use DX3B
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name
        task_e = tasks_by_name["E"]
        device_e = task_e.devices["device_1"]
        assert device_e.name == device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="E", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "E")
        await task_manager.complete_task(db, experiment_name, "E")

        # Step 5: F references E.device_1 - must use DX3B
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name
        task_f = tasks_by_name["F"]
        device_f = task_f.devices["device_1"]
        assert device_f.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="F", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "F")
        await task_manager.complete_task(db, experiment_name, "F")

        # Step 6: G references A.device_1 and D.device_1
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name
        task_g = tasks_by_name["G"]
        assert len(task_g.devices) == 2
        device_g_analyzer = task_g.devices["analyzer"]
        device_g_processor = task_g.devices["processor"]
        assert device_g_analyzer.name == device_a.name
        assert device_g_processor.name == device_d.name
        await task_manager.create_task(db, TaskSubmission(name="G", type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, "G")
        await task_manager.complete_task(db, experiment_name, "G")

        assert await cpsat_scheduler.is_experiment_completed(db, experiment_name)


@pytest.mark.parametrize("setup_lab_experiment", [("dynamic_lab", "dynamic_resource_experiment")], indirect=True)
class TestCpSatSchedulerDynamicContainers:
    @pytest.mark.asyncio
    async def test_dynamic_container_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        experiment_type = "dynamic_resource_experiment"
        experiment_name = "dyn_cont_cp_1"

        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=experiment_type, name=experiment_name, owner="test", priority=0)
        )
        await experiment_manager.start_experiment(db, experiment_name)

        graph = ExperimentGraph(configuration_manager.experiments[experiment_type])
        await cpsat_scheduler.register_experiment(experiment_name, experiment_type, graph)

        # Step 1: A requires dynamic beaker_500
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
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
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
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
        tasks = await cpsat_scheduler.request_tasks(db, experiment_name)
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

        # Confirm experiment completion
        assert await cpsat_scheduler.is_experiment_completed(db, experiment_name)
        assert len(await cpsat_scheduler.request_tasks(db, experiment_name)) == 0


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", EXPERIMENT_TYPE)], indirect=True)
class TestCpSatSchedulerContinuation:
    async def _create_and_start_experiment(
        self, db, experiment_manager, experiment_name: str = "experiment_1", priority: int = 0
    ):
        await experiment_manager.create_experiment(
            db, ExperimentSubmission(type=EXPERIMENT_TYPE, name=experiment_name, owner="test", priority=priority)
        )
        await experiment_manager.start_experiment(db, experiment_name)

    async def _complete_task(self, db, task_manager, task_name: str, experiment_name: str = "experiment_1"):
        await task_manager.create_task(db, TaskSubmission(name=task_name, type="Noop", experiment_name=experiment_name))
        await task_manager.start_task(db, experiment_name, task_name)
        await task_manager.complete_task(db, experiment_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        assert task.name == expected.task_name
        device = task.devices["device_1"]
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self, db, scheduler, allocation_manager, task_manager, experiment_name: str, expected_tasks: list[ExpectedTask]
    ):
        tasks = await scheduler.request_tasks(db, experiment_name)
        if not tasks:
            tasks = await scheduler.request_tasks(db, experiment_name)
        tasks_by_name = {task.name: task for task in tasks}
        for expected in expected_tasks:
            task = tasks_by_name.get(expected.task_name)
            assert task is not None, f"Expected task with id {expected.task_name} not found"
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, experiment_name)

    @pytest.mark.asyncio
    async def test_multi_experiment_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        """Test experiment scheduling workflow with multiple experiments and soft priorities."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        await self._create_and_start_experiment(db, experiment_manager, "experiment_1", priority=5)
        await self._create_and_start_experiment(db, experiment_manager, "experiment_2", priority=0)

        await cpsat_scheduler.register_experiment("experiment_1", EXPERIMENT_TYPE, experiment_graph)
        await cpsat_scheduler.register_experiment("experiment_2", EXPERIMENT_TYPE, experiment_graph)

        # EX1-A
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_1",
            [ExpectedTask("A", "abstract_lab", "D1")],
        )

        # EX1-B, EX1-C and EX2-A
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_1",
            [ExpectedTask("B", "abstract_lab", "D2"), ExpectedTask("C", "abstract_lab", "D3")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("A", "abstract_lab", "D1")],
        )

        # EX1-D and EX2-B
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_1",
            [ExpectedTask("D", "abstract_lab", "D3")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("B", "abstract_lab", "D2")],
        )

        # EX1-F and EX1-E
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_1",
            [ExpectedTask("F", "abstract_lab", "D3"), ExpectedTask("E", "abstract_lab", "D4")],
        )

        # EX1-G and EX2-C
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_1",
            [ExpectedTask("G", "abstract_lab", "D5")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("C", "abstract_lab", "D3")],
        )

        # EX2-D
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("D", "abstract_lab", "D3")],
        )

        # EX2-F and EX2-E
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("F", "abstract_lab", "D3"), ExpectedTask("E", "abstract_lab", "D4")],
        )

        # EX2-G
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "experiment_2",
            [ExpectedTask("G", "abstract_lab", "D5")],
        )

    @pytest.mark.asyncio
    async def test_task_groups_scheduled_consecutively(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        experiment_manager,
        task_manager,
        allocation_manager,
    ):
        """Test that tasks in the same group are scheduled consecutively without gaps"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        experiment = configuration_manager.experiments["abstract_experiment_2"]
        experiment.tasks[0].group = "preprocessing"  # A
        experiment.tasks[1].group = "preprocessing"  # B (depends on A)
        experiment.tasks[2].group = "preprocessing"  # C (depends on A)
        experiment.tasks[3].group = None  # D
        experiment.tasks[4].group = "analysis"  # E
        experiment.tasks[5].group = "analysis"  # F
        experiment.tasks[6].group = None  # G

        experiment_graph = ExperimentGraph(experiment)
        await self._create_and_start_experiment(db, experiment_manager)
        await cpsat_scheduler.register_experiment("experiment_1", EXPERIMENT_TYPE, experiment_graph)

        await cpsat_scheduler.request_tasks(db, "experiment_1")

        schedule = cpsat_scheduler._schedule["experiment_1"]
        durations = cpsat_scheduler._task_durations["experiment_1"]

        # Verify preprocessing group (A, B, C) are consecutive
        a_end = schedule["A"] + durations["A"]
        b_start = schedule["B"]
        b_end = b_start + durations["B"]
        c_start = schedule["C"]
        c_end = c_start + durations["C"]

        assert b_start >= a_end
        assert c_start >= a_end
        assert a_end in (b_start, c_start)
        if b_start == a_end:
            assert c_start == b_end
        else:
            assert b_start == c_end

        # Verify analysis group (E, F) are consecutive
        e_start = schedule["E"]
        e_end = e_start + durations["E"]
        f_start = schedule["F"]
        f_end = f_start + durations["F"]
        assert (f_start == e_end) or (e_start == f_end)

    @pytest.mark.asyncio
    async def test_task_groups_across_experiments(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        experiment_manager,
        allocation_manager,
    ):
        """Test that task groups are experiment-specific"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        exp1_config = copy.deepcopy(configuration_manager.experiments["abstract_experiment_2"])
        exp2_config = copy.deepcopy(configuration_manager.experiments["abstract_experiment_2"])

        for task in exp1_config.tasks:
            task.group = "processing" if task.name in ["A", "B"] else None
        for task in exp2_config.tasks:
            task.group = "processing" if task.name in ["C", "D"] else None

        graph_1 = ExperimentGraph(exp1_config)
        graph_2 = ExperimentGraph(exp2_config)

        await self._create_and_start_experiment(db, experiment_manager, "exp1", priority=1)
        await self._create_and_start_experiment(db, experiment_manager, "exp2", priority=1)
        await cpsat_scheduler.register_experiment("exp1", EXPERIMENT_TYPE, graph_1)
        await cpsat_scheduler.register_experiment("exp2", EXPERIMENT_TYPE, graph_2)

        await cpsat_scheduler.request_tasks(db, "exp1")
        await cpsat_scheduler.request_tasks(db, "exp2")

        schedule_1 = cpsat_scheduler._schedule["exp1"]
        durations_1 = cpsat_scheduler._task_durations["exp1"]

        # Verify exp1 tasks A and B are consecutive
        assert schedule_1["B"] == schedule_1["A"] + durations_1["A"]

        # Verify groups don't interfere across experiments
        assert "exp1" in cpsat_scheduler._schedule
        assert "exp2" in cpsat_scheduler._schedule
