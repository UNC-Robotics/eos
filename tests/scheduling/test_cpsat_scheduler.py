import copy
from typing import NamedTuple

from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *

PROTOCOL = "abstract_protocol_2"


class ExpectedTask(NamedTuple):
    """Helper class to define expected task scheduling results"""

    task_name: str
    lab_name: str
    device_name: str


@pytest.fixture()
def protocol_graph(configuration_manager):
    protocol = configuration_manager.protocols["abstract_protocol_2"]
    return ProtocolGraph(protocol)


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", PROTOCOL)], indirect=True)
class TestCpSatScheduler:
    @pytest.mark.asyncio
    async def test_register_protocol_run(self, cpsat_scheduler, protocol_graph):
        await cpsat_scheduler.register_protocol_run("run1", PROTOCOL, protocol_graph)
        assert cpsat_scheduler._registered_protocol_runs["run1"] == (
            PROTOCOL,
            protocol_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_protocol_run(self, cpsat_scheduler, protocol_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.register_protocol_run("run1", "invalid_type", protocol_graph)

    @pytest.mark.asyncio
    async def test_unregister_protocol_run(self, db, cpsat_scheduler, protocol_graph, setup_lab_protocol):
        # Register protocol run
        await cpsat_scheduler.register_protocol_run("run1", PROTOCOL, protocol_graph)
        assert "run1" in cpsat_scheduler._registered_protocol_runs

        # Unregister protocol run
        await cpsat_scheduler.unregister_protocol_run(db, "run1")
        assert "run1" not in cpsat_scheduler._registered_protocol_runs

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_protocol_run(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.unregister_protocol_run(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_protocol_run(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_protocol_run(
        self, db, protocol_run_manager, protocol_run_name: str = "protocol_run_1", priority: int = 0
    ):
        """Helper to create and start a protocol run"""
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name=protocol_run_name, owner="test", priority=priority)
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

    async def _complete_task(self, db, task_manager, task_name: str, protocol_run_name: str = "protocol_run_1"):
        """Helper to mark a task as completed"""
        await task_manager.create_task(
            db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, task_name)
        await task_manager.complete_task(db, protocol_run_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        """Helper to verify a scheduled task matches expectations"""
        assert task.name == expected.task_name
        device = task.devices["device_1"]
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self,
        db,
        scheduler,
        allocation_manager,
        task_manager,
        protocol_run_name: str,
        expected_tasks: list[ExpectedTask],
    ):
        """Helper to process and verify a batch of scheduled tasks (order not enforced)"""
        tasks = await scheduler.request_tasks(db, protocol_run_name)
        if not tasks:
            tasks = await scheduler.request_tasks(db, protocol_run_name)

        tasks_by_name = {task.name: task for task in tasks}

        # Verify each expected task exists and then complete it
        for expected in expected_tasks:
            task = tasks_by_name.get(expected.task_name)
            assert task is not None, f"Expected task with id {expected.task_name} not found"
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, protocol_run_name)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        protocol_graph,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        """Test complete protocol run scheduling workflow"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Setup protocol run
        await self._create_and_start_protocol_run(db, protocol_run_manager)
        await cpsat_scheduler.register_protocol_run("protocol_run_1", PROTOCOL, protocol_graph)

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
                db, cpsat_scheduler, allocation_manager, task_manager, "protocol_run_1", expected_batch
            )

        # Verify protocol run completion
        assert await cpsat_scheduler.is_protocol_run_completed(db, "protocol_run_1")

        # Verify no more tasks are scheduled
        final_tasks = await cpsat_scheduler.request_tasks(db, "protocol_run_1")
        assert len(final_tasks) == 0


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_device_protocol")], indirect=True)
class TestCpSatSchedulerDynamicDevices:
    @pytest.mark.asyncio
    async def test_dynamic_device_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        """Verify CP-SAT schedules tasks with dynamic device allocation, respecting constraints."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Create and start protocol run
        protocol = "dynamic_device_protocol"
        protocol_run_name = "dyn_run_1"
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test", priority=0)
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        # Register protocol run
        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await cpsat_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: Task A requires a DT3 device dynamically
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)

        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.devices) == 1
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}
        assert device_a.lab_name == "dynamic_lab"

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "A")
        await task_manager.complete_task(db, protocol_run_name, "A")

        # Step 2: B (DT2) and C (DT3 with allowed_devices=DX3B)
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.devices) == 1
        device_b = task_b.devices["device_1"]
        assert device_b.lab_name == "dynamic_lab"
        assert device_b.name in {"DY2A", "DY2B"}
        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "B")
        await task_manager.complete_task(db, protocol_run_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.devices) == 1
        device_c = task_c.devices["device_1"]
        assert device_c.name == "DX3B"
        assert device_c.lab_name == "dynamic_lab"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "C")
        await task_manager.complete_task(db, protocol_run_name, "C")

        # Step 3: D (DT5)
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        assert len(task_d.devices) == 1
        device_d = task_d.devices["device_1"]
        assert device_d.lab_name == "dynamic_lab"
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "D")
        await task_manager.complete_task(db, protocol_run_name, "D")

        # Steps 4-6: E, F, G
        for task_name in ["E", "F", "G"]:
            tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
            tasks_by_name = {t.name: t for t in tasks}
            assert task_name in tasks_by_name
            await task_manager.create_task(
                db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name)
            )
            await task_manager.start_task(db, protocol_run_name, task_name)
            await task_manager.complete_task(db, protocol_run_name, task_name)

        # Verify protocol run completion
        assert await cpsat_scheduler.is_protocol_run_completed(db, protocol_run_name)
        assert len(await cpsat_scheduler.request_tasks(db, protocol_run_name)) == 0


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_device_protocol")], indirect=True)
class TestCpSatSchedulerDeviceReferences:
    @pytest.mark.asyncio
    async def test_device_reference_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        """Verify CP-SAT device references ensure same device is used across dependent tasks."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        protocol = "dynamic_device_protocol"
        protocol_run_name = "dev_ref_cpsat_run_1"

        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test", priority=0)
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await cpsat_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: Task A dynamically allocates a DT3 device
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "A")
        await task_manager.complete_task(db, protocol_run_name, "A")

        # Step 2: B and C (C must get DX3B)
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "B")
        await task_manager.complete_task(db, protocol_run_name, "B")

        task_c = tasks_by_name["C"]
        device_c = task_c.devices["device_1"]
        assert device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "C")
        await task_manager.complete_task(db, protocol_run_name, "C")

        # Step 3: D
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        device_d = task_d.devices["device_1"]
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "D")
        await task_manager.complete_task(db, protocol_run_name, "D")

        # Step 4: E references C.device_1 - must use DX3B
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name
        task_e = tasks_by_name["E"]
        device_e = task_e.devices["device_1"]
        assert device_e.name == device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="E", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "E")
        await task_manager.complete_task(db, protocol_run_name, "E")

        # Step 5: F references E.device_1 - must use DX3B
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name
        task_f = tasks_by_name["F"]
        device_f = task_f.devices["device_1"]
        assert device_f.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="F", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "F")
        await task_manager.complete_task(db, protocol_run_name, "F")

        # Step 6: G references A.device_1 and D.device_1
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name
        task_g = tasks_by_name["G"]
        assert len(task_g.devices) == 2
        device_g_analyzer = task_g.devices["analyzer"]
        device_g_processor = task_g.devices["processor"]
        assert device_g_analyzer.name == device_a.name
        assert device_g_processor.name == device_d.name
        await task_manager.create_task(db, TaskSubmission(name="G", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "G")
        await task_manager.complete_task(db, protocol_run_name, "G")

        assert await cpsat_scheduler.is_protocol_run_completed(db, protocol_run_name)


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_resource_protocol")], indirect=True)
class TestCpSatSchedulerDynamicContainers:
    @pytest.mark.asyncio
    async def test_dynamic_container_allocation(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        protocol = "dynamic_resource_protocol"
        protocol_run_name = "dyn_cont_cp_1"

        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test", priority=0)
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await cpsat_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: A requires dynamic beaker_500
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        if not tasks:
            tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.resources) == 1
        res_a = next(iter(task_a.resources.values()))
        assert res_a in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskSubmission(name="A", type="Container Usage", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, "A")
        await task_manager.complete_task(db, protocol_run_name, "A")

        # Step 2: B (dynamic beaker_500) and C (specific B500B)
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.resources) == 1
        res_b = next(iter(task_b.resources.values()))
        assert res_b in {"B500A", "B500B", "B500C"}
        await task_manager.create_task(
            db, TaskSubmission(name="B", type="Container Usage", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, "B")
        await task_manager.complete_task(db, protocol_run_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.resources) == 1
        res_c = next(iter(task_c.resources.values()))
        assert res_c == "B500B"
        await task_manager.create_task(
            db, TaskSubmission(name="C", type="Container Usage", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, "C")
        await task_manager.complete_task(db, protocol_run_name, "C")

        # Step 3: D (dynamic vial)
        tasks = await cpsat_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        assert len(task_d.resources) == 1
        res_d = next(iter(task_d.resources.values()))
        assert res_d in {"VIAL1", "VIAL2"}
        await task_manager.create_task(
            db, TaskSubmission(name="D", type="Container Vial Usage", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, "D")
        await task_manager.complete_task(db, protocol_run_name, "D")

        # Confirm protocol run completion
        assert await cpsat_scheduler.is_protocol_run_completed(db, protocol_run_name)
        assert len(await cpsat_scheduler.request_tasks(db, protocol_run_name)) == 0


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", PROTOCOL)], indirect=True)
class TestCpSatSchedulerContinuation:
    async def _create_and_start_protocol_run(
        self, db, protocol_run_manager, protocol_run_name: str = "protocol_run_1", priority: int = 0
    ):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name=protocol_run_name, owner="test", priority=priority)
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

    async def _complete_task(self, db, task_manager, task_name: str, protocol_run_name: str = "protocol_run_1"):
        await task_manager.create_task(
            db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name)
        )
        await task_manager.start_task(db, protocol_run_name, task_name)
        await task_manager.complete_task(db, protocol_run_name, task_name)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        assert task.name == expected.task_name
        device = task.devices["device_1"]
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self,
        db,
        scheduler,
        allocation_manager,
        task_manager,
        protocol_run_name: str,
        expected_tasks: list[ExpectedTask],
    ):
        tasks = await scheduler.request_tasks(db, protocol_run_name)
        if not tasks:
            tasks = await scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {task.name: task for task in tasks}
        for expected in expected_tasks:
            task = tasks_by_name.get(expected.task_name)
            assert task is not None, f"Expected task with id {expected.task_name} not found"
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, protocol_run_name)

    @pytest.mark.asyncio
    async def test_multi_protocol_run_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        protocol_graph,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        """Test protocol run scheduling workflow with multiple protocol runs and soft priorities."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        await self._create_and_start_protocol_run(db, protocol_run_manager, "protocol_run_1", priority=5)
        await self._create_and_start_protocol_run(db, protocol_run_manager, "protocol_run_2", priority=0)

        await cpsat_scheduler.register_protocol_run("protocol_run_1", PROTOCOL, protocol_graph)
        await cpsat_scheduler.register_protocol_run("protocol_run_2", PROTOCOL, protocol_graph)

        # RUN1-A
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_1",
            [ExpectedTask("A", "abstract_lab", "D1")],
        )

        # RUN1-B, RUN1-C and RUN2-A
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_1",
            [ExpectedTask("B", "abstract_lab", "D2"), ExpectedTask("C", "abstract_lab", "D3")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("A", "abstract_lab", "D1")],
        )

        # RUN1-D and RUN2-B
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_1",
            [ExpectedTask("D", "abstract_lab", "D3")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("B", "abstract_lab", "D2")],
        )

        # RUN1-F and RUN1-E
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_1",
            [ExpectedTask("F", "abstract_lab", "D3"), ExpectedTask("E", "abstract_lab", "D4")],
        )

        # RUN1-G and RUN2-C
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_1",
            [ExpectedTask("G", "abstract_lab", "D5")],
        )
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("C", "abstract_lab", "D3")],
        )

        # RUN2-D
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("D", "abstract_lab", "D3")],
        )

        # RUN2-F and RUN2-E
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("F", "abstract_lab", "D3"), ExpectedTask("E", "abstract_lab", "D4")],
        )

        # RUN2-G
        await self._process_and_verify_tasks(
            db,
            cpsat_scheduler,
            allocation_manager,
            task_manager,
            "protocol_run_2",
            [ExpectedTask("G", "abstract_lab", "D5")],
        )

    @pytest.mark.asyncio
    async def test_task_groups_scheduled_consecutively(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        """Test that tasks in the same group are scheduled consecutively without gaps"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        protocol = configuration_manager.protocols["abstract_protocol_2"]
        protocol.tasks[0].group = "preprocessing"  # A
        protocol.tasks[1].group = "preprocessing"  # B (depends on A)
        protocol.tasks[2].group = "preprocessing"  # C (depends on A)
        protocol.tasks[3].group = None  # D
        protocol.tasks[4].group = "analysis"  # E
        protocol.tasks[5].group = "analysis"  # F
        protocol.tasks[6].group = None  # G

        protocol_graph = ProtocolGraph(protocol)
        await self._create_and_start_protocol_run(db, protocol_run_manager)
        await cpsat_scheduler.register_protocol_run("protocol_run_1", PROTOCOL, protocol_graph)

        await cpsat_scheduler.request_tasks(db, "protocol_run_1")

        schedule = cpsat_scheduler._schedule["protocol_run_1"]
        durations = cpsat_scheduler._task_durations["protocol_run_1"]

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
    async def test_task_groups_across_protocol_runs(
        self,
        db,
        cpsat_scheduler,
        configuration_manager,
        protocol_run_manager,
        allocation_manager,
    ):
        """Test that task groups are protocol-run-specific"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        run1_config = copy.deepcopy(configuration_manager.protocols["abstract_protocol_2"])
        run2_config = copy.deepcopy(configuration_manager.protocols["abstract_protocol_2"])

        for task in run1_config.tasks:
            task.group = "processing" if task.name in ["A", "B"] else None
        for task in run2_config.tasks:
            task.group = "processing" if task.name in ["C", "D"] else None

        graph_1 = ProtocolGraph(run1_config)
        graph_2 = ProtocolGraph(run2_config)

        await self._create_and_start_protocol_run(db, protocol_run_manager, "run1", priority=1)
        await self._create_and_start_protocol_run(db, protocol_run_manager, "run2", priority=1)
        await cpsat_scheduler.register_protocol_run("run1", PROTOCOL, graph_1)
        await cpsat_scheduler.register_protocol_run("run2", PROTOCOL, graph_2)

        await cpsat_scheduler.request_tasks(db, "run1")
        await cpsat_scheduler.request_tasks(db, "run2")

        schedule_1 = cpsat_scheduler._schedule["run1"]
        durations_1 = cpsat_scheduler._task_durations["run1"]

        # Verify run1 tasks A and B are consecutive
        assert schedule_1["B"] == schedule_1["A"] + durations_1["A"]

        # Verify groups don't interfere across protocol runs
        assert "run1" in cpsat_scheduler._schedule
        assert "run2" in cpsat_scheduler._schedule
