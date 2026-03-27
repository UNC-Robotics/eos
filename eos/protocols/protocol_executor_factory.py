from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.protocol_graph import ProtocolGraph
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class ProtocolExecutorFactory:
    """
    Factory class to create ProtocolExecutor instances.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        protocol_run_manager: ProtocolRunManager,
        task_manager: TaskManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._protocol_run_manager = protocol_run_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._db_interface = db_interface

    def create(self, protocol_run_submission: ProtocolRunSubmission, campaign: str | None = None) -> ProtocolExecutor:
        protocol = self._configuration_manager.protocols.get(protocol_run_submission.type)
        protocol_graph = ProtocolGraph(protocol)

        return ProtocolExecutor(
            protocol_run_submission=protocol_run_submission,
            protocol_graph=protocol_graph,
            protocol_run_manager=self._protocol_run_manager,
            task_manager=self._task_manager,
            task_executor=self._task_executor,
            scheduler=self._scheduler,
            db_interface=self._db_interface,
            campaign=campaign,
        )
