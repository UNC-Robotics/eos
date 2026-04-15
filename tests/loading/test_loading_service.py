import asyncio
from typing import Any
from unittest.mock import patch

import ray
from sqlalchemy import select, delete

from eos.configuration.entities.definition import DefinitionModel
from eos.configuration.entities.task_def import DeviceAssignmentDef
from eos.devices.base_device import BaseDevice
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceModel
from eos.devices.exceptions import EosDeviceInitializationError
from eos.orchestration.services.loading_service import LoadingService
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.resources.entities.resource import ResourceModel
from eos.resources.resource_manager import ResourceManager
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.base_task import BaseTask
from eos.tasks.entities.task import TaskSubmission
from eos.tasks.task_manager import TaskManager
from tests.fixtures import *

LAB_NAME = "small_lab"
DEVICE_NAMES = {"general_computer", "magnetic_mixer", "magnetic_mixer_2", "evaporator", "substance_fridge"}


def make_failing_create(failing_device_names: set[str]):
    """Create a patched _create_device_actor that fails for specific devices."""
    original = DeviceManager._create_device_actor

    async def patched(self, device):
        if device.name in failing_device_names:
            self._cleanup_failed_actor(device.get_actor_name())
            self._error_collector.batch_error(
                f"Simulated failure for '{device.get_actor_name()}'",
                EosDeviceInitializationError,
            )
            return None
        return await original(self, device)

    return patched


@pytest.fixture
async def loading_env(configuration_manager, db_interface, file_db_interface, clear_db):
    """Set up LoadingService with real dependencies."""
    dm = DeviceManager(configuration_manager=configuration_manager)
    rm = ResourceManager(configuration_manager=configuration_manager)
    prm = ProtocolRunManager(configuration_manager=configuration_manager)
    tm = TaskManager(configuration_manager=configuration_manager, file_db_interface=file_db_interface)

    async with db_interface.get_async_session() as session:
        await configuration_manager.def_sync.sync_all_defs(session)

    service = LoadingService(
        configuration_manager=configuration_manager,
        device_manager=dm,
        resource_manager=rm,
        protocol_run_manager=prm,
        task_manager=tm,
    )
    yield service, dm, configuration_manager

    # Cleanup: actors, DB records, in-memory config
    async with db_interface.get_async_session() as session:
        await dm.cleanup_device_actors(session)
        await session.execute(delete(DeviceModel))
        await session.execute(delete(ResourceModel))
    if LAB_NAME in configuration_manager.labs:
        configuration_manager.unload_lab(LAB_NAME)


async def _get_lab_loaded(db, lab_name: str) -> bool:
    result = await db.execute(
        select(DefinitionModel.is_loaded).where(DefinitionModel.type == "lab", DefinitionModel.name == lab_name)
    )
    return result.scalar() is True


async def _get_device_count(db, lab_name: str) -> int:
    result = await db.execute(select(DeviceModel).where(DeviceModel.lab_name == lab_name))
    return len(result.scalars().all())


def _get_actor_names_for_lab(dm: DeviceManager, lab_name: str) -> set[str]:
    return {name for name in dm._device_actor_handles if name.partition(".")[0] == lab_name}


class TestLoadLabs:
    @pytest.mark.asyncio
    async def test_load_lab_success(self, loading_env, db):
        service, dm, cm = loading_env

        await service.load_labs(db, {LAB_NAME})

        assert LAB_NAME in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == {f"{LAB_NAME}.{d}" for d in DEVICE_NAMES}
        assert await _get_device_count(db, LAB_NAME) == len(DEVICE_NAMES)
        assert await _get_lab_loaded(db, LAB_NAME) is True

    @pytest.mark.asyncio
    async def test_partial_failure_rolls_back(self, loading_env, db):
        service, dm, cm = loading_env

        with (
            patch.object(DeviceManager, "_create_device_actor", make_failing_create({"evaporator"})),
            pytest.raises(EosDeviceInitializationError),
        ):
            await service.load_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == set()
        assert await _get_device_count(db, LAB_NAME) == 0
        assert await _get_lab_loaded(db, LAB_NAME) is False

    @pytest.mark.asyncio
    async def test_all_devices_fail_rolls_back(self, loading_env, db):
        service, dm, cm = loading_env

        with (
            patch.object(DeviceManager, "_create_device_actor", make_failing_create(DEVICE_NAMES)),
            pytest.raises(EosDeviceInitializationError),
        ):
            await service.load_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == set()
        assert await _get_device_count(db, LAB_NAME) == 0
        assert await _get_lab_loaded(db, LAB_NAME) is False

    @pytest.mark.asyncio
    async def test_retry_after_failure(self, loading_env, db):
        service, dm, cm = loading_env

        # First attempt fails
        with (
            patch.object(DeviceManager, "_create_device_actor", make_failing_create({"evaporator"})),
            pytest.raises(EosDeviceInitializationError),
        ):
            await service.load_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs

        # Second attempt succeeds
        await service.load_labs(db, {LAB_NAME})

        assert LAB_NAME in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == {f"{LAB_NAME}.{d}" for d in DEVICE_NAMES}
        assert await _get_device_count(db, LAB_NAME) == len(DEVICE_NAMES)
        assert await _get_lab_loaded(db, LAB_NAME) is True


class TestUnloadLabs:
    @pytest.mark.asyncio
    async def test_unload_loaded_lab(self, loading_env, db):
        service, dm, cm = loading_env

        await service.load_labs(db, {LAB_NAME})
        await service.unload_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == set()
        assert await _get_device_count(db, LAB_NAME) == 0
        assert await _get_lab_loaded(db, LAB_NAME) is False

    @pytest.mark.asyncio
    async def test_unload_not_in_memory(self, loading_env, db):
        """Unloading a lab not in ConfigurationManager should still clean up DB without crashing."""
        service, _dm, cm = loading_env

        # Manually mark loaded in DB without loading in ConfigurationManager
        await db.execute(
            DefinitionModel.__table__.update()
            .where(DefinitionModel.type == "lab", DefinitionModel.name == LAB_NAME)
            .values(is_loaded=True)
        )
        await db.commit()

        await service.unload_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs
        assert await _get_lab_loaded(db, LAB_NAME) is False


class TestReloadLabs:
    @pytest.mark.asyncio
    async def test_reload_success(self, loading_env, db):
        service, dm, cm = loading_env

        await service.load_labs(db, {LAB_NAME})
        await service.reload_labs(db, {LAB_NAME})

        assert LAB_NAME in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == {f"{LAB_NAME}.{d}" for d in DEVICE_NAMES}
        assert await _get_lab_loaded(db, LAB_NAME) is True

    @pytest.mark.asyncio
    async def test_reload_failure_leaves_unloaded(self, loading_env, db):
        service, dm, cm = loading_env

        await service.load_labs(db, {LAB_NAME})

        with (
            patch.object(DeviceManager, "_create_device_actor", make_failing_create({"evaporator"})),
            pytest.raises(EosDeviceInitializationError),
        ):
            await service.reload_labs(db, {LAB_NAME})

        assert LAB_NAME not in cm.labs
        assert _get_actor_names_for_lab(dm, LAB_NAME) == set()
        assert await _get_lab_loaded(db, LAB_NAME) is False


class TestReloadDevices:
    @pytest.mark.asyncio
    async def test_reload_device_picks_up_new_behavior(self, loading_env, db):
        """After reloading a device, the new actor should have updated behavior."""
        service, dm, _cm = loading_env

        await service.load_labs(db, {LAB_NAME})

        # Verify original evaporator report returns None
        actor = dm.get_device_actor(LAB_NAME, "evaporator")
        report_before = await actor.report.remote()
        assert report_before is None

        # Define a new evaporator class with different behavior
        class EvaporatorV2(BaseDevice):
            async def _initialize(self, init_parameters: dict[str, Any]) -> None:
                pass

            async def _cleanup(self) -> None:
                pass

            async def _report(self) -> dict[str, Any]:
                return {"version": 2}

        # Patch reload_plugin to inject the new class without touching disk
        original_reload = dm._device_plugin_registry.reload_plugin

        def mock_reload(device_type: str) -> None:
            if device_type == "evaporator":
                dm._device_plugin_registry.plugin_types[device_type] = EvaporatorV2
            else:
                original_reload(device_type)

        with patch.object(dm._device_plugin_registry, "reload_plugin", mock_reload):
            await service.reload_devices(db, LAB_NAME, ["evaporator"])

        # Verify new actor has updated behavior
        new_actor = dm.get_device_actor(LAB_NAME, "evaporator")
        report_after = await new_actor.report.remote()
        assert report_after == {"version": 2}

        # Other devices should be unaffected
        assert f"{LAB_NAME}.magnetic_mixer" in dm._device_actor_handles


class TestReloadTaskPlugins:
    @staticmethod
    async def _execute_task(task_executor, task_def, task_name):
        """Execute a task and return its output parameters."""
        task_submission = TaskSubmission.from_def(task_def, "water_purification")
        task_submission.name = task_name
        scheduled_task = ScheduledTask(
            name=task_name,
            protocol_run_name="water_purification",
            devices=task_def.devices,
            resources={},
        )

        future = asyncio.create_task(task_executor.request_task_execution(task_submission, scheduled_task))

        timeout = asyncio.create_task(asyncio.sleep(10))
        while not future.done() and not timeout.done():
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)
        if timeout.done() and not future.done():
            raise TimeoutError("Task processing timed out")

        output_params, _, _ = await future
        return output_params

    @pytest.mark.asyncio
    @pytest.mark.parametrize("setup_lab_protocol", [(LAB_NAME, "water_purification")], indirect=True)
    async def test_reload_task_picks_up_new_behavior(
        self,
        setup_lab_protocol,
        task_executor,
        protocol_run_manager,
        protocol_graph,
        db_interface,
        configuration_manager,
    ):
        """After reloading a task plugin, executing the task should use the new behavior."""
        async with db_interface.get_async_session() as db:
            await protocol_run_manager.create_protocol_run(
                db,
                ProtocolRunSubmission(
                    type="water_purification",
                    name="water_purification",
                    owner="test",
                ),
            )

        task = protocol_graph.get_task("mixing")
        task.parameters["time"] = 5
        task.devices = {
            "magnetic_mixer": DeviceAssignmentDef(lab_name=LAB_NAME, name="magnetic_mixer"),
        }

        # Execute with original plugin
        output_before = await self._execute_task(task_executor, task, "mixing_v1")
        assert output_before == {"mixing_time": 5}

        # Reload with a new task class that adds a "version" field
        class MagneticMixingV2(BaseTask):
            async def _execute(self, devices, parameters, resources):
                return {"mixing_time": parameters["time"], "version": 2}, None, None

        task_registry = configuration_manager.tasks
        original_reload = task_registry.reload_plugin

        def mock_reload(task_type: str) -> None:
            if task_type == "Magnetic Mixing":
                task_registry.plugin_types[task_type] = MagneticMixingV2
            else:
                original_reload(task_type)

        with patch.object(task_registry, "reload_plugin", mock_reload):
            task_registry.reload_plugin("Magnetic Mixing")

        # Execute with reloaded plugin — should have the new behavior
        output_after = await self._execute_task(task_executor, task, "mixing_v2")
        assert output_after == {"mixing_time": 5, "version": 2}
