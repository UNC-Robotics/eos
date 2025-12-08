import asyncio

import ray
import time

from eos.campaigns.campaign_executor_factory import CampaignExecutorFactory
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.eos_config import DatabaseType, EosConfig
from eos.resources.resource_manager import ResourceManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.orchestration.services.campaign_service import CampaignService
from eos.orchestration.services.experiment_service import ExperimentService
from eos.orchestration.services.lab_service import LabService
from eos.orchestration.services.loading_service import LoadingService
from eos.orchestration.services.result_service import ResultService
from eos.orchestration.services.task_service import TaskService
from eos.orchestration.work_signal import WorkSignal

from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.database.file_db_interface import FileDbInterface
from eos.database.postgresql_db_interface import PostgresqlDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.allocation.allocation_manager import (
    AllocationManager,
)
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.scheduler_factory import SchedulerFactory
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import get_di_container
from eos.utils.di.di_deps import get_device_manager, get_db_interface
from eos.utils.singleton import Singleton


class Orchestrator(metaclass=Singleton):
    """
    The top-level orchestrator that initializes and manages all EOS components.
    """

    def __init__(
        self,
        config: EosConfig,
    ):
        self._user_dir = config.user_dir
        self._packages = config.packages
        self._scheduler_config = config.scheduler
        self._db_config = config.db
        self._file_db_config = config.file_db

        self._initialized = False

        self._task_executor: TaskExecutor | None = None
        self._on_demand_task_executor: OnDemandTaskExecutor | None = None

        self._loading: LoadingService | None = None
        self._labs: LabService | None = None
        self._results: ResultService | None = None
        self._tasks: TaskService | None = None
        self._experiments: ExperimentService | None = None
        self._campaigns: CampaignService | None = None

        self._work_signal: WorkSignal | None = None

    async def initialize(self) -> None:
        """
        Prepare the orchestrator. This is required before any other operations can be performed.
        """
        if self._initialized:
            return

        log.info("Initializing EOS...")

        di = get_di_container()

        # Configuration ###########################################
        configuration_manager = ConfigurationManager(self._user_dir, self._packages if self._packages else None)
        di.register(ConfigurationManager, configuration_manager)

        # Persistence #############################################
        if self._db_config.type == DatabaseType.POSTGRESQL:
            db_interface = PostgresqlDbInterface(self._db_config)
        elif self._db_config.type == DatabaseType.SQLITE:
            db_interface = SqliteDbInterface(self._db_config)
        else:
            raise ValueError(f"Unsupported database type '{self._db_config.type}'")
        di.register(AbstractSqlDbInterface, db_interface)

        await db_interface.initialize_database()

        async with db_interface.get_async_session() as db:
            await configuration_manager.spec_sync.sync_all_specs(db)
            await configuration_manager.spec_sync.cleanup_deleted_specs(db)

        file_db_interface = FileDbInterface(self._file_db_config)
        di.register(FileDbInterface, file_db_interface)

        # Ray cluster ############################################
        self._initialize_ray()

        # Work signal for event-driven wake-up
        self._work_signal = WorkSignal()
        di.register(WorkSignal, self._work_signal)

        # State management ########################################
        device_manager = DeviceManager()
        async with db_interface.get_async_session() as db:
            await device_manager.cleanup_devices(db)
        di.register(DeviceManager, device_manager)

        resource_manager = ResourceManager()
        async with db_interface.get_async_session() as db:
            await resource_manager.initialize(db)
        di.register(ResourceManager, resource_manager)

        allocation_manager = AllocationManager()
        async with db_interface.get_async_session() as db:
            await allocation_manager.initialize(db)
        di.register(AllocationManager, allocation_manager)

        task_manager = TaskManager()
        di.register(TaskManager, task_manager)

        experiment_manager = ExperimentManager()
        di.register(ExperimentManager, experiment_manager)

        campaign_manager = CampaignManager()
        di.register(CampaignManager, campaign_manager)

        campaign_optimizer_manager = CampaignOptimizerManager()
        di.register(CampaignOptimizerManager, campaign_optimizer_manager)

        # Execution ###############################################
        task_executor = TaskExecutor()
        di.register(TaskExecutor, task_executor)
        self._task_executor = task_executor

        on_demand_task_executor = OnDemandTaskExecutor()
        di.register(OnDemandTaskExecutor, on_demand_task_executor)
        self._on_demand_task_executor = on_demand_task_executor

        # Scheduler
        log.info(f"Using scheduler: {self._scheduler_config.type.value}")
        scheduler = SchedulerFactory.create_scheduler(self._scheduler_config.type)
        if self._scheduler_config.parameters:
            await scheduler.update_parameters(self._scheduler_config.parameters)
        di.register(AbstractScheduler, scheduler)

        experiment_executor_factory = ExperimentExecutorFactory()
        di.register(ExperimentExecutorFactory, experiment_executor_factory)

        campaign_executor_factory = CampaignExecutorFactory()
        di.register(CampaignExecutorFactory, campaign_executor_factory)

        # Orchestrator Services ###################################
        self._loading = LoadingService()
        self._labs = LabService()
        self._results = ResultService()
        self._tasks = TaskService()
        self._experiments = ExperimentService()
        self._campaigns = CampaignService()

        await self._fail_running_work()

        self._initialized = True

    @staticmethod
    def _initialize_ray() -> None:
        try:
            ray.init(address="auto", namespace="eos", ignore_reinit_error=True)
            log.info("Connected to Ray cluster.")

            cluster_resources = ray.cluster_resources()
            if "eos" not in cluster_resources:
                ray.shutdown()
                raise Exception(
                    "The 'eos' custom Ray resource not found in the cluster. "
                    "Please ensure the cluster head node is configured to provide the custom Ray resource 'eos'."
                )

        except ConnectionError:
            log.info("Initializing local Ray cluster...")
            ray.init(namespace="eos", resources={"eos": 1000})
            log.info("Initialized local Ray cluster.")

    async def terminate(self) -> None:
        """
        Terminate the orchestrator. After this, no other operations can be performed.
        This should be called before the program exits.
        """
        if not self._initialized:
            return
        log.info("Cleaning up devices...")

        async with get_db_interface().get_async_session() as db:
            await get_device_manager().cleanup_device_actors(db)

        log.info("Shutting down Ray node...")
        ray.shutdown()
        self._initialized = False

    async def spin(self, rate_hz: float = 10, maintenance_interval: float = 60.0) -> None:
        """
        Event-driven spin with rate limiting when busy.

        :param rate_hz: Processing rate when work is present.
        :param maintenance_interval: Timeout for maintenance wake-ups when idle.
        """
        cycle_time = 1 / rate_hz

        while True:
            start = time.time()

            has_work = (
                bool(self._experiments.submitted_experiments)
                or bool(self._campaigns.submitted_campaigns)
                or bool(self._task_executor.has_work)
                or bool(self._on_demand_task_executor.has_work)
            )

            if not has_work:
                await self._work_signal.wait(max_wait=maintenance_interval)
            self._work_signal.clear()

            try:
                await self.spin_once()
            except Exception as e:
                log.error(f"Error in orchestrator spin loop: {e}", exc_info=True)

            elapsed = time.time() - start
            has_more_work = (
                bool(self._experiments.submitted_experiments)
                or bool(self._campaigns.submitted_campaigns)
                or bool(self._task_executor.has_work)
                or bool(self._on_demand_task_executor.has_work)
            )

            if has_more_work and elapsed < cycle_time:
                await asyncio.sleep(cycle_time - elapsed)

    async def spin_once(self) -> None:
        """Process submitted work."""
        await self._experiments.process_experiment_cancellations()
        await self._campaigns.process_campaign_cancellations()

        await self._task_executor.process_tasks()

        await self._tasks.process_on_demand_tasks()

        await self._experiments.process_experiments()
        await self._campaigns.process_campaigns()

        await asyncio.sleep(0)
        await self._task_executor.process_new_tasks()

    async def _fail_running_work(self) -> None:
        """
        When the orchestrator starts, fail all running tasks, experiments, and campaigns.
        This is for safety, as if the orchestrator was terminated while there was running work then the state of the
        system may be unknown. We want to force manual review of the state of the system and explicitly require
        re-submission of any work that was running.
        """
        async with get_db_interface().get_async_session() as db:
            await self._tasks.fail_running_tasks(db)
            await self._experiments.fail_running_experiments(db)
            await self._campaigns.fail_running_campaigns(db)

    @property
    def db_interface(self) -> AbstractSqlDbInterface:
        return get_db_interface()

    @property
    def loading(self) -> LoadingService:
        return self._loading

    @property
    def labs(self) -> LabService:
        return self._labs

    @property
    def results(self) -> ResultService:
        return self._results

    @property
    def tasks(self) -> TaskService:
        return self._tasks

    @property
    def experiments(self) -> ExperimentService:
        return self._experiments

    @property
    def campaigns(self) -> CampaignService:
        return self._campaigns
