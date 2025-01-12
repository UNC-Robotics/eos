from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.experiments.entities.experiment import ExperimentDefinition
from eos.experiments.experiment_executor import ExperimentExecutor
from eos.experiments.experiment_manager import ExperimentManager
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject_all


class ExperimentExecutorFactory:
    """
    Factory class to create ExperimentExecutor instances.
    """

    @inject_all
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._task_manager = task_manager
        self._task_executor = task_executor
        self._scheduler = scheduler
        self._db_interface = db_interface

    def create(self, experiment_definition: ExperimentDefinition) -> ExperimentExecutor:
        experiment_config = self._configuration_manager.experiments.get(experiment_definition.type)
        experiment_graph = ExperimentGraph(experiment_config)

        return ExperimentExecutor(
            experiment_definition=experiment_definition,
            experiment_graph=experiment_graph,
            experiment_manager=self._experiment_manager,
            task_manager=self._task_manager,
            task_executor=self._task_executor,
            scheduler=self._scheduler,
            db_interface=self._db_interface,
        )
