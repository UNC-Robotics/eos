from typing import NamedTuple

from eos.protocols.entities.protocol_run import ProtocolRunSubmission
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
def protocol_graph(configuration_manager):
    protocol = configuration_manager.protocols["abstract_protocol"]
    return ProtocolGraph(protocol)


@pytest.mark.parametrize("setup_lab_protocol", [("abstract_lab", "abstract_protocol")], indirect=True)
class TestGreedyScheduler:
    @pytest.mark.asyncio
    async def test_register_protocol_run(self, greedy_scheduler, protocol_graph):
        await greedy_scheduler.register_protocol_run("run1", "abstract_protocol", protocol_graph)
        assert greedy_scheduler._registered_protocol_runs["run1"] == (
            "abstract_protocol",
            protocol_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_protocol_run(self, greedy_scheduler, protocol_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.register_protocol_run("run1", "invalid_type", protocol_graph)

    @pytest.mark.asyncio
    async def test_unregister_protocol_run(self, db, greedy_scheduler, protocol_graph, setup_lab_protocol):
        await greedy_scheduler.register_protocol_run("run1", "abstract_protocol", protocol_graph)
        assert "run1" in greedy_scheduler._registered_protocol_runs
        await greedy_scheduler.unregister_protocol_run(db, "run1")
        assert "run1" not in greedy_scheduler._registered_protocol_runs

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_protocol_run(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.unregister_protocol_run(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_protocol_run(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_protocol_run(self, db, protocol_run_manager, protocol_run_name: str = "protocol_run_1"):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type="abstract_protocol", name=protocol_run_name, owner="test")
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
        device = next(iter(task.devices.values()))
        assert device.lab_name == expected.lab_name
        assert device.name == expected.device_name

    async def _process_and_verify_tasks(
        self, db, scheduler, task_manager, protocol_run_name: str, expected_tasks: list[ExpectedTask]
    ):
        tasks = await scheduler.request_tasks(db, protocol_run_name)

        assert len(tasks) == len(expected_tasks)
        for task, expected in zip(tasks, expected_tasks, strict=False):
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_name, protocol_run_name)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        greedy_scheduler,
        protocol_graph,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        await self._create_and_start_protocol_run(db, protocol_run_manager)
        await greedy_scheduler.register_protocol_run("protocol_run_1", "abstract_protocol", protocol_graph)

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
            await self._process_and_verify_tasks(db, greedy_scheduler, task_manager, "protocol_run_1", expected_batch)

        assert await greedy_scheduler.is_protocol_run_completed(db, "protocol_run_1")

        final_tasks = await greedy_scheduler.request_tasks(db, "protocol_run_1")
        assert len(final_tasks) == 0


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_device_protocol")], indirect=True)
class TestGreedySchedulerDynamicDevices:
    @pytest.mark.asyncio
    async def test_dynamic_device_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        protocol = "dynamic_device_protocol"
        protocol_run_name = "dyn_run_1"

        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test")
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await greedy_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: Task A requires a DT3 device dynamically
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        assert len(task_a.devices) == 1
        device_a = next(iter(task_a.devices.values()))
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}
        assert device_a.lab_name == "dynamic_lab"

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "A")
        await task_manager.complete_task(db, protocol_run_name, "A")

        # Step 2: B (DT2) and C (DT3 with allowed_devices=DX3B)
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert {"B", "C"}.issubset(tasks_by_name.keys())

        task_b = tasks_by_name["B"]
        assert len(task_b.devices) == 1
        device_b = next(iter(task_b.devices.values()))
        assert device_b.lab_name == "dynamic_lab"
        assert device_b.name in {"DY2A", "DY2B"}
        await task_manager.create_task(db, TaskSubmission(name="B", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "B")
        await task_manager.complete_task(db, protocol_run_name, "B")

        task_c = tasks_by_name["C"]
        assert len(task_c.devices) == 1
        device_c = next(iter(task_c.devices.values()))
        assert device_c.name == "DX3B"
        assert device_c.lab_name == "dynamic_lab"
        await task_manager.create_task(db, TaskSubmission(name="C", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "C")
        await task_manager.complete_task(db, protocol_run_name, "C")

        # Steps 3-6: D, E, F, G
        for task_name in ["D", "E", "F", "G"]:
            tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
            tasks_by_name = {t.name: t for t in tasks}
            assert task_name in tasks_by_name
            await task_manager.create_task(
                db, TaskSubmission(name=task_name, type="Noop", protocol_run_name=protocol_run_name)
            )
            await task_manager.start_task(db, protocol_run_name, task_name)
            await task_manager.complete_task(db, protocol_run_name, task_name)

        assert await greedy_scheduler.is_protocol_run_completed(db, protocol_run_name)
        assert len(await greedy_scheduler.request_tasks(db, protocol_run_name)) == 0


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_device_protocol")], indirect=True)
class TestGreedySchedulerDeviceReferences:
    @pytest.mark.asyncio
    async def test_device_reference_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        protocol = "dynamic_device_protocol"
        protocol_run_name = "dev_ref_run_1"

        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test")
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await greedy_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: A dynamically allocates DT3
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "A" in tasks_by_name
        task_a = tasks_by_name["A"]
        device_a = task_a.devices["device_1"]
        assert device_a.name in {"DX3A", "DX3B", "DX3C", "DX3D"}

        await task_manager.create_task(db, TaskSubmission(name="A", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "A")
        await task_manager.complete_task(db, protocol_run_name, "A")

        # Step 2: B and C (C must get DX3B)
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
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
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "D" in tasks_by_name
        task_d = tasks_by_name["D"]
        device_d = task_d.devices["device_1"]
        assert device_d.name in {"DZ5A", "DZ5B"}
        await task_manager.create_task(db, TaskSubmission(name="D", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "D")
        await task_manager.complete_task(db, protocol_run_name, "D")

        # Step 4: E references C.device_1 -> DX3B
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "E" in tasks_by_name
        task_e = tasks_by_name["E"]
        device_e = task_e.devices["device_1"]
        assert device_e.name == device_c.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="E", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "E")
        await task_manager.complete_task(db, protocol_run_name, "E")

        # Step 5: F references E.device_1 -> DX3B
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "F" in tasks_by_name
        task_f = tasks_by_name["F"]
        device_f = task_f.devices["device_1"]
        assert device_f.name == "DX3B"
        await task_manager.create_task(db, TaskSubmission(name="F", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "F")
        await task_manager.complete_task(db, protocol_run_name, "F")

        # Step 6: G references A.device_1 and D.device_1
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
        tasks_by_name = {t.name: t for t in tasks}
        assert "G" in tasks_by_name
        task_g = tasks_by_name["G"]
        assert len(task_g.devices) == 2
        assert task_g.devices["analyzer"].name == device_a.name
        assert task_g.devices["processor"].name == device_d.name
        await task_manager.create_task(db, TaskSubmission(name="G", type="Noop", protocol_run_name=protocol_run_name))
        await task_manager.start_task(db, protocol_run_name, "G")
        await task_manager.complete_task(db, protocol_run_name, "G")

        assert await greedy_scheduler.is_protocol_run_completed(db, protocol_run_name)


@pytest.mark.parametrize("setup_lab_protocol", [("dynamic_lab", "dynamic_resource_protocol")], indirect=True)
class TestGreedySchedulerDynamicContainers:
    @pytest.mark.asyncio
    async def test_dynamic_container_allocation(
        self,
        db,
        greedy_scheduler,
        configuration_manager,
        protocol_run_manager,
        task_manager,
        allocation_manager,
    ):
        protocol = "dynamic_resource_protocol"
        protocol_run_name = "dyn_cont_1"

        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=protocol, name=protocol_run_name, owner="test")
        )
        await protocol_run_manager.start_protocol_run(db, protocol_run_name)

        graph = ProtocolGraph(configuration_manager.protocols[protocol])
        await greedy_scheduler.register_protocol_run(protocol_run_name, protocol, graph)

        # Step 1: A requires dynamic beaker_500
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
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
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
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
        tasks = await greedy_scheduler.request_tasks(db, protocol_run_name)
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

        assert await greedy_scheduler.is_protocol_run_completed(db, protocol_run_name)
        assert len(await greedy_scheduler.request_tasks(db, protocol_run_name)) == 0
