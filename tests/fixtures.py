import os
import tempfile
from pathlib import Path

import pytest
import ray
import yaml

from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.eos_config import DbConfig
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.containers.container_manager import ContainerManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.file_db_interface import FileDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.resource_allocation.container_allocation_manager import ContainerAllocationManager
from eos.resource_allocation.device_allocation_manager import DeviceAllocationManager
from eos.resource_allocation.resource_allocation_manager import (
    ResourceAllocationManager,
)
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager

log.set_level("INFO")


def load_test_config():
    config_path = Path(__file__).resolve().parent / "test_config.yml"

    if not config_path.exists():
        raise FileNotFoundError(f"Test config file not found at {config_path}")

    with Path(config_path).open("r") as file:
        return yaml.safe_load(file)


@pytest.fixture(scope="session")
def configuration_manager():
    config = load_test_config()
    root_dir = Path(__file__).resolve().parent.parent
    user_dir = root_dir / config["user_dir"]
    os.chdir(root_dir)
    return ConfigurationManager(user_dir=str(user_dir))


@pytest.fixture(scope="session")
def task_specification_registry(configuration_manager):
    return configuration_manager.task_specs


@pytest.fixture
def user_dir():
    config = load_test_config()
    root_dir = Path(__file__).resolve().parent.parent
    return root_dir / config["user_dir"]


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
async def db_interface(temp_dir_manager):
    """Create a database interface with a temporary directory for SQLite files."""
    config = load_test_config()

    db_config = DbConfig(
        db_type=config["db"]["db_type"],
        db_name=config["db"]["db_name"],
        sqlite_in_memory=True,
    )

    db = SqliteDbInterface(db_config)
    await db.initialize_database()
    return db


@pytest.fixture
async def db(db_interface):
    async with db_interface.get_async_session() as db:
        yield db


@pytest.fixture(scope="session")
def file_db_interface(db_interface):
    config = load_test_config()
    file_db_credentials = DbConfig(**config["file_db"])
    return FileDbInterface(file_db_credentials, bucket_name="test-eos")


@pytest.fixture
def setup_lab_experiment(request, configuration_manager):
    lab_name, experiment_name = request.param

    if lab_name not in configuration_manager.labs:
        configuration_manager.load_lab(lab_name)
    lab_config = configuration_manager.labs[lab_name]

    if experiment_name not in configuration_manager.experiments:
        configuration_manager.load_experiment(experiment_name)
    experiment_config = configuration_manager.experiments[experiment_name]

    return lab_config, experiment_config


@pytest.fixture
def experiment_graph(setup_lab_experiment):
    _, experiment_config = setup_lab_experiment

    return ExperimentGraph(
        experiment_config,
    )


@pytest.fixture
async def clear_db(db_interface):
    await db_interface.clear_db()


@pytest.fixture
async def container_manager(setup_lab_experiment, configuration_manager, db_interface, clear_db):
    container_manager = ContainerManager(configuration_manager=configuration_manager)
    async with db_interface.get_async_session() as db:
        await container_manager.initialize(db)
    return container_manager


@pytest.fixture
async def device_manager(setup_lab_experiment, configuration_manager, db, clear_db):
    device_manager = DeviceManager(configuration_manager)

    await device_manager.update_devices(db, loaded_labs=set(configuration_manager.labs.keys()))
    yield device_manager
    await device_manager.cleanup_device_actors(db)


@pytest.fixture
async def experiment_manager(setup_lab_experiment, configuration_manager, clear_db):
    return ExperimentManager(configuration_manager)


@pytest.fixture
async def container_allocation_manager(setup_lab_experiment, configuration_manager, clear_db):
    return ContainerAllocationManager(configuration_manager)


@pytest.fixture
async def device_allocation_manager(setup_lab_experiment, configuration_manager, clear_db):
    return DeviceAllocationManager(configuration_manager)


@pytest.fixture
async def resource_allocation_manager(setup_lab_experiment, configuration_manager, db_interface, clear_db):
    resource_allocation_manager = ResourceAllocationManager(configuration_manager, db_interface)
    async with db_interface.get_async_session() as db:
        await resource_allocation_manager.initialize(db)
    return resource_allocation_manager


@pytest.fixture
async def task_manager(setup_lab_experiment, configuration_manager, file_db_interface, clear_db):
    return TaskManager(configuration_manager, file_db_interface)


@pytest.fixture(scope="session", autouse=True)
def ray_cluster():
    if not ray.is_initialized():
        ray.init(namespace="test-eos", resources={"eos-core": 1000})
    yield
    ray.shutdown()


@pytest.fixture
def task_executor(
    setup_lab_experiment,
    task_manager,
    device_manager,
    container_manager,
    resource_allocation_manager,
    configuration_manager,
    db_interface,
):
    return TaskExecutor(
        task_manager,
        device_manager,
        container_manager,
        resource_allocation_manager,
        configuration_manager,
        db_interface,
    )


@pytest.fixture
def on_demand_task_executor(
    setup_lab_experiment,
    task_executor,
    task_manager,
):
    return OnDemandTaskExecutor(task_executor, task_manager)


@pytest.fixture
def greedy_scheduler(
    setup_lab_experiment,
    configuration_manager,
    experiment_manager,
    task_manager,
    device_manager,
    resource_allocation_manager,
):
    return GreedyScheduler(
        configuration_manager, experiment_manager, task_manager, device_manager, resource_allocation_manager
    )


@pytest.fixture
def experiment_executor_factory(
    configuration_manager,
    experiment_manager,
    task_manager,
    task_executor,
    greedy_scheduler,
    db_interface,
):
    return ExperimentExecutorFactory(
        configuration_manager=configuration_manager,
        experiment_manager=experiment_manager,
        task_manager=task_manager,
        task_executor=task_executor,
        scheduler=greedy_scheduler,
        db_interface=db_interface,
    )


@pytest.fixture
async def campaign_manager(setup_lab_experiment, configuration_manager, clear_db):
    return CampaignManager(configuration_manager)


@pytest.fixture
async def campaign_optimizer_manager(
    configuration_manager,
):
    return CampaignOptimizerManager(configuration_manager)
