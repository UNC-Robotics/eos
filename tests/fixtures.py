import asyncio
import contextlib
import os
import tempfile
from pathlib import Path

import pytest
import ray
import yaml
from dotenv import load_dotenv

from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.eos_config import EosConfig
from eos.configuration.protocol_graph import ProtocolGraph
from eos.resources.resource_manager import ResourceManager
from eos.devices.device_manager import DeviceManager
from eos.protocols.protocol_executor_factory import ProtocolExecutorFactory
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.database.file_db_interface import FileDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.allocation.allocation_manager import AllocationManager
from eos.allocation.entities.device_allocation import DeviceAllocationModel
from eos.devices.entities.device import DeviceModel
from sqlalchemy import delete, event
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.scheduling.cpsat_scheduler import CpSatScheduler
from eos.scheduling.heuristic_scheduler import HeuristicScheduler
from eos.orchestration.work_signal import WorkSignal
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager

log.set_level("WARNING")

TEST_PLAN_TIME_BUDGET_S = 0.05  # Heuristic planning for test-sized protocols needs no more


@contextlib.contextmanager
def count_statements(db_interface):
    """Count SQL statements sent to the database inside the block."""
    statements: list[str] = []
    engine = db_interface._async_engine.sync_engine

    def record(conn, cursor, statement, *args) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _background_work(scheduler) -> asyncio.Future | None:
    """The scheduler's in-flight CP-SAT solve or heuristic plan, if any."""
    if (solve := getattr(scheduler, "_pending_solve", None)) is not None:
        return solve[0]
    return getattr(scheduler, "_pending_plan", None)


async def request_tasks(scheduler, db, protocol_run_name: str) -> list:
    """Request tasks, waiting out background solves and plans so tests see their result."""
    tasks = await scheduler.request_tasks(db, protocol_run_name)
    while (pending := _background_work(scheduler)) is not None:
        await asyncio.wait({pending})  # Failures surface through the scheduler, not here
        tasks += await scheduler.request_tasks(db, protocol_run_name)
    return tasks


def load_test_config() -> EosConfig:
    """Load the test configuration and return it as an EosConfig object."""
    tests_dir = Path(__file__).resolve().parent
    load_dotenv(tests_dir / ".env")

    config_path = tests_dir / "test_config.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"Test config file not found at {config_path}")

    with config_path.open("r") as file:
        user_config = yaml.safe_load(file) or {}

    return EosConfig.model_validate(user_config)


@pytest.fixture(scope="session")
def eos_config() -> EosConfig:
    """Load the test configuration once per session as an EosConfig fixture."""
    return load_test_config()


@pytest.fixture(scope="session")
def user_dir(eos_config):
    return eos_config.user_dir


@pytest.fixture(scope="session")
def configuration_manager(eos_config):
    """Provides a ConfigurationManager using the session-scoped EosConfig."""
    root_dir = Path(__file__).resolve().parent.parent
    user_dir = root_dir / eos_config.user_dir
    os.chdir(root_dir)
    return ConfigurationManager(user_dir=str(user_dir))


@pytest.fixture(scope="session")
def task_specification_registry(configuration_manager):
    return configuration_manager.task_specs


class TempDirManager:
    """Manages temporary directory creation and cleanup for tests."""

    def __init__(self):
        self.temp_dir = None

    def create(self) -> Path:
        """Create a new temporary directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        return self.temp_dir

    def cleanup(self):
        """Clean up the temporary directory and its contents."""
        if self.temp_dir and self.temp_dir.exists():
            try:
                for file in self.temp_dir.glob("*"):
                    file.unlink()
                self.temp_dir.rmdir()
            except Exception as e:
                log.warning(f"Failed to cleanup temporary directory: {e}")


@pytest.fixture(scope="session")
def temp_dir_manager():
    """Provides a temporary directory manager that persists for the test session."""
    manager = TempDirManager()
    yield manager
    manager.cleanup()


@pytest.fixture(scope="session")
async def db_interface(eos_config):
    """Create a database interface with a temporary directory for SQLite files."""
    db = SqliteDbInterface(eos_config.db)
    await db.initialize_database()
    return db


@pytest.fixture
async def db(db_interface):
    async with db_interface.get_async_session() as db:
        yield db


@pytest.fixture(scope="session")
def file_db_interface(eos_config, db_interface):
    return FileDbInterface(eos_config.file_db)


@pytest.fixture(scope="class")
def setup_lab_protocol(request, configuration_manager):
    lab_name, protocol_name = request.param

    if lab_name not in configuration_manager.labs:
        configuration_manager.load_lab(lab_name)
    lab = configuration_manager.labs[lab_name]

    if protocol_name not in configuration_manager.protocols:
        configuration_manager.load_protocol(protocol_name)
    protocol = configuration_manager.protocols[protocol_name]

    return lab, protocol


@pytest.fixture
def protocol_graph(setup_lab_protocol):
    _, protocol = setup_lab_protocol

    return ProtocolGraph(
        protocol,
    )


@pytest.fixture
async def clear_db(db_interface):
    await db_interface.clear_db()


@pytest.fixture
async def resource_manager(setup_lab_protocol, configuration_manager, db_interface, clear_db):
    resource_manager = ResourceManager(configuration_manager=configuration_manager)
    async with db_interface.get_async_session() as db:
        await resource_manager.initialize(db)
    return resource_manager


def _device_models(configuration_manager, actor_names=None) -> list[DeviceModel]:
    """DB records for the devices of loaded labs, optionally only those with the given actor names."""
    return [
        DeviceModel(
            name=device_name,
            lab_name=lab_name,
            type=lab_device.type,
            computer=lab_device.computer,
            meta=lab_device.meta or {},
        )
        for lab_name, lab in configuration_manager.labs.items()
        for device_name, lab_device in lab.devices.items()
        if actor_names is None or f"{lab_name}.{device_name}" in actor_names
    ]


async def _is_reusable(name: str, handle, configuration_manager) -> bool:
    """Whether a cached device actor still belongs to a loaded lab, is registered under its name and responds."""
    lab_name, _, device_name = name.partition(".")
    if device_name not in getattr(configuration_manager.labs.get(lab_name), "devices", {}):
        return False
    try:
        if ray.get_actor(name)._actor_id != handle._actor_id:
            return False
        await asyncio.wait_for(handle.get_status.remote(), timeout=2)
    except Exception:
        return False
    return True


# Device actors created by these fixtures. Each test module gets its own session fixtures through
# `from tests.fixtures import *`, so modules adopt each other's actors instead of recreating them.
_FIXTURE_DEVICE_ACTOR_IDS = set()


@pytest.fixture(scope="session")
def session_device_manager(configuration_manager):
    """Device actors take about 70 ms each to start, so test classes reuse them."""
    return DeviceManager(configuration_manager=configuration_manager)


@pytest.fixture(scope="class")
async def class_device_manager(setup_lab_protocol, session_device_manager, configuration_manager, db_interface):
    """Ensure device actors exist for all loaded labs, reusing healthy ones from earlier classes."""
    dm = session_device_manager
    for name, handle in list(dm._device_actor_handles.items()):
        if not await _is_reusable(name, handle, configuration_manager):
            with contextlib.suppress(Exception):
                ray.kill(handle)
            dm._remove_device_references(name)

    # Actors left by other device managers (e.g. in loading tests) would otherwise be adopted
    for lab_name, lab in configuration_manager.labs.items():
        for device_name in lab.devices:
            name = f"{lab_name}.{device_name}"
            if name not in dm._device_actor_handles:
                with contextlib.suppress(ValueError):
                    actor = ray.get_actor(name)
                    if actor._actor_id not in _FIXTURE_DEVICE_ACTOR_IDS:
                        ray.kill(actor)

    async with db_interface.get_async_session() as session:
        await session.execute(delete(DeviceAllocationModel))
        await session.execute(delete(DeviceModel))
        session.add_all(_device_models(configuration_manager, dm._device_actor_handles))  # Marks them as existing
        await dm.create_devices_for_labs(session, set(configuration_manager.labs.keys()))
    _FIXTURE_DEVICE_ACTOR_IDS.update(handle._actor_id for handle in dm._device_actor_handles.values())
    yield dm
    async with db_interface.get_async_session() as session:
        await session.execute(delete(DeviceAllocationModel))


@pytest.fixture
async def device_manager(class_device_manager, setup_lab_protocol, db, db_interface, clear_db):
    """Function-scoped wrapper: reuses the device actors and re-inserts the device records wiped by clear_db."""
    dm = class_device_manager
    db.add_all(_device_models(dm._configuration_manager))
    await db.flush()
    yield dm
    await db.execute(delete(DeviceAllocationModel))


@pytest.fixture
async def protocol_run_manager(setup_lab_protocol, configuration_manager, clear_db):
    return ProtocolRunManager(configuration_manager)


@pytest.fixture
async def allocation_manager(
    setup_lab_protocol, configuration_manager, db_interface, device_manager, resource_manager, clear_db
):
    allocation_manager = AllocationManager(configuration_manager, db_interface)
    async with db_interface.get_async_session() as db:
        await allocation_manager.initialize(db)
    return allocation_manager


@pytest.fixture
async def task_manager(setup_lab_protocol, configuration_manager, file_db_interface, clear_db):
    return TaskManager(configuration_manager, file_db_interface)


@pytest.fixture(scope="session", autouse=True)
def ray_cluster():
    if not ray.is_initialized():
        ray.init(namespace="test-eos", resources={"eos": 1000}, include_dashboard=False)
    yield
    ray.shutdown()


@pytest.fixture
def work_signal():
    return WorkSignal()


@pytest.fixture
def task_executor(
    setup_lab_protocol,
    task_manager,
    device_manager,
    resource_manager,
    configuration_manager,
    greedy_scheduler,
    db_interface,
    work_signal,
    eos_config,
):
    return TaskExecutor(
        task_manager,
        device_manager,
        resource_manager,
        configuration_manager,
        greedy_scheduler,
        db_interface,
        work_signal,
        eos_config.file_db,
        eos_config.execution,
    )


@pytest.fixture
def greedy_scheduler(
    setup_lab_protocol,
    configuration_manager,
    protocol_run_manager,
    task_manager,
    device_manager,
    allocation_manager,
):
    return GreedyScheduler(
        configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
    )


@pytest.fixture
async def heuristic_scheduler(
    setup_lab_protocol,
    configuration_manager,
    protocol_run_manager,
    task_manager,
    device_manager,
    allocation_manager,
):
    scheduler = HeuristicScheduler(
        configuration_manager, protocol_run_manager, task_manager, device_manager, allocation_manager
    )
    await scheduler.update_parameters({"time_budget_s": TEST_PLAN_TIME_BUDGET_S})
    return scheduler


@pytest.fixture
async def cpsat_scheduler(
    setup_lab_protocol,
    configuration_manager,
    protocol_run_manager,
    task_manager,
    device_manager,
    allocation_manager,
):
    scheduler = CpSatScheduler(
        configuration_manager,
        protocol_run_manager,
        task_manager,
        device_manager,
        allocation_manager,
    )
    await scheduler.update_parameters({"warm_start_budget_s": TEST_PLAN_TIME_BUDGET_S})
    yield scheduler
    scheduler._discard_pending_solve()  # Otherwise closing the event loop waits for the solve thread


@pytest.fixture
def protocol_executor_factory(
    configuration_manager,
    protocol_run_manager,
    task_manager,
    task_executor,
    cpsat_scheduler,
    db_interface,
):
    return ProtocolExecutorFactory(
        configuration_manager=configuration_manager,
        protocol_run_manager=protocol_run_manager,
        task_manager=task_manager,
        task_executor=task_executor,
        scheduler=cpsat_scheduler,
        db_interface=db_interface,
    )


@pytest.fixture
async def campaign_manager(setup_lab_protocol, configuration_manager, clear_db):
    return CampaignManager(configuration_manager)


@pytest.fixture
async def campaign_optimizer_manager(
    configuration_manager,
    eos_config,
):
    return CampaignOptimizerManager(configuration_manager, eos_config.execution)
