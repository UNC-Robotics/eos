import asyncio
import ray

from eos.campaigns.campaign_executor_factory import CampaignExecutorFactory
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.eos_config import DbConfig
from eos.containers.container_manager import ContainerManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.monitoring.graceful_termination_monitor import GracefulTerminationMonitor
from eos.orchestration.modules.campaign_module import CampaignModule
from eos.orchestration.modules.experiment_module import ExperimentModule
from eos.orchestration.modules.lab_module import LabModule
from eos.orchestration.modules.loading_module import LoadingModule
from eos.orchestration.modules.result_module import ResultModule
from eos.orchestration.modules.task_module import TaskModule
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.persistence.file_db_interface import FileDbInterface
from eos.resource_allocation.resource_allocation_manager import (
    ResourceAllocationManager,
)
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.singleton import Singleton


class Orchestrator(metaclass=Singleton):
    """
    The top-level orchestrator that initializes and manages all EOS components.
    """

    def __init__(
        self,
        user_dir: str,
        db_credentials: DbConfig,
        file_db_credentials: DbConfig,
    ):
        self._user_dir = user_dir
        self._db_credentials = db_credentials
        self._file_db_credentials = file_db_credentials

        self._initialized = False

        self._configuration_manager: ConfigurationManager | None = None
        self._db_interface: AsyncMongoDbInterface | None = None
        self._file_db_interface: FileDbInterface | None = None
        self._graceful_termination_monitor: GracefulTerminationMonitor | None = None
        self._device_manager: DeviceManager | None = None
        self._container_manager: ContainerManager | None = None
        self._resource_allocation_manager: ResourceAllocationManager | None = None
        self._task_manager: TaskManager | None = None
        self._experiment_manager: ExperimentManager | None = None
        self._campaign_manager: CampaignManager | None = None
        self._campaign_optimizer_manager: CampaignOptimizerManager | None = None
        self._task_executor: TaskExecutor | None = None
        self._on_demand_task_executor: OnDemandTaskExecutor | None = None
        self._scheduler: GreedyScheduler | None = None
        self._experiment_executor_factory: ExperimentExecutorFactory | None = None
        self._campaign_executor_factory: CampaignExecutorFactory | None = None

        self._loading: LoadingModule | None = None
        self._labs: LabModule | None = None
        self._results: ResultModule | None = None
        self._tasks: TaskModule | None = None
        self._experiments: ExperimentModule | None = None
        self._campaigns: CampaignModule | None = None

    async def initialize(self) -> None:
        """
        Prepare the orchestrator. This is required before any other operations can be performed.
        """
        if self._initialized:
            return

        log.info("Initializing EOS...")
        log.info("Initializing Ray cluster...")
        ray.init(namespace="eos", resources={"eos-core": 1000})
        log.info("Ray cluster initialized.")

        # Configuration ###########################################
        self._configuration_manager = ConfigurationManager(self._user_dir)

        # Persistence #############################################
        self._db_interface = AsyncMongoDbInterface(self._db_credentials)
        self._file_db_interface = FileDbInterface(self._file_db_credentials)

        # State management ########################################
        self._graceful_termination_monitor = GracefulTerminationMonitor(self._db_interface)
        await self._graceful_termination_monitor.initialize()

        self._device_manager = DeviceManager(self._configuration_manager, self._db_interface)
        await self._device_manager.initialize(self._db_interface)

        self._container_manager = ContainerManager(self._configuration_manager, self._db_interface)
        await self._container_manager.initialize(self._db_interface)

        self._resource_allocation_manager = ResourceAllocationManager(self._db_interface)
        await self._resource_allocation_manager.initialize(self._configuration_manager, self._db_interface)

        self._task_manager = TaskManager(self._configuration_manager, self._db_interface, self._file_db_interface)
        await self._task_manager.initialize(self._db_interface)

        self._experiment_manager = ExperimentManager(self._configuration_manager, self._db_interface)
        await self._experiment_manager.initialize(self._db_interface)

        self._campaign_manager = CampaignManager(self._configuration_manager, self._db_interface)
        await self._campaign_manager.initialize(self._db_interface)

        self._campaign_optimizer_manager = CampaignOptimizerManager(self._configuration_manager, self._db_interface)
        await self._campaign_optimizer_manager.initialize(self._db_interface)

        # Execution ###############################################
        self._task_executor = TaskExecutor(
            self._task_manager,
            self._device_manager,
            self._container_manager,
            self._resource_allocation_manager,
            self._configuration_manager,
        )
        self._on_demand_task_executor = OnDemandTaskExecutor(
            self._task_executor, self._task_manager, self._container_manager
        )
        self._scheduler = GreedyScheduler(
            self._configuration_manager,
            self._experiment_manager,
            self._task_manager,
            self._device_manager,
            self._resource_allocation_manager,
        )
        self._experiment_executor_factory = ExperimentExecutorFactory(
            self._configuration_manager,
            self._experiment_manager,
            self._task_manager,
            self._container_manager,
            self._task_executor,
            self._scheduler,
        )
        self._campaign_executor_factory = CampaignExecutorFactory(
            self._configuration_manager,
            self._campaign_manager,
            self._campaign_optimizer_manager,
            self._task_manager,
            self._experiment_executor_factory,
        )

        # Orchestrator Modules #######################################
        self._loading = LoadingModule(
            self._configuration_manager, self._device_manager, self._container_manager, self._experiment_manager
        )
        self._labs = LabModule(self._configuration_manager)
        self._results = ResultModule(self._task_manager)
        self._tasks = TaskModule(
            self._configuration_manager, self._task_manager, self._task_executor, self._on_demand_task_executor
        )
        self._experiments = ExperimentModule(
            self._configuration_manager, self._experiment_manager, self._experiment_executor_factory
        )
        self._campaigns = CampaignModule(
            self._configuration_manager, self._campaign_manager, self._campaign_executor_factory
        )

        await self._fail_running_work()

        self._initialized = True

    async def terminate(self) -> None:
        """
        Terminate the orchestrator. After this, no other operations can be performed.
        This should be called before the program exits.
        """
        if not self._initialized:
            return
        log.info("Cleaning up devices...")
        await self._device_manager.cleanup_device_actors()
        log.info("Shutting down Ray cluster...")
        ray.shutdown()
        await self._graceful_termination_monitor.set_terminated_gracefully()
        self._initialized = False

    async def spin(self, rate_hz: int = 5) -> None:
        """
        Spin the orchestrator at a given rate in Hz. Process submitted work.

        :param rate_hz: The processing rate in Hz. This is the rate in which the orchestrator updates.
        """
        while True:
            await self._experiments.process_experiment_cancellations()
            await self._campaigns.process_campaign_cancellations()

            await asyncio.gather(
                self._tasks.process_on_demand_tasks(),
                self._experiments.process_experiments(),
                self._campaigns.process_campaigns(),
            )

            await self._resource_allocation_manager.process_active_requests()

            await asyncio.sleep(1 / rate_hz)

    async def _fail_running_work(self) -> None:
        """
        When the orchestrator starts, fail all running tasks, experiments, and campaigns.
        This is for safety, as if the orchestrator was terminated while there was running work then the state of the
        system may be unknown. We want to force manual review of the state of the system and explicitly require
        re-submission of any work that was running.
        """
        await self._tasks.fail_running_tasks()
        await self._experiments.fail_running_experiments()
        await self._campaigns.fail_running_campaigns()

    @property
    def loading(self) -> LoadingModule:
        return self._loading

    @property
    def labs(self) -> LabModule:
        return self._labs

    @property
    def results(self) -> ResultModule:
        return self._results

    @property
    def tasks(self) -> TaskModule:
        return self._tasks

    @property
    def experiments(self) -> ExperimentModule:
        return self._experiments

    @property
    def campaigns(self) -> CampaignModule:
        return self._campaigns
