from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.containers.container_manager import ContainerManager
from eos.experiments.entities.experiment import ExperimentDefinition
from eos.experiments.experiment_executor import ExperimentExecutor
from eos.experiments.experiment_manager import ExperimentManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager


class ExperimentExecutorFactory:
    """
    Factory class to create ExperimentExecutor instances.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        container_manager: ContainerManager,
        task_executor: TaskExecutor,
        scheduler: AbstractScheduler,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._task_manager = task_manager
        self._container_manager = container_manager
        self._task_executor = task_executor
        self._scheduler = scheduler

    def create(self, experiment_definition: ExperimentDefinition) -> ExperimentExecutor:
        experiment_config = self._configuration_manager.experiments.get(experiment_definition.type)
        experiment_graph = ExperimentGraph(experiment_config)

        return ExperimentExecutor(
            experiment_definition=experiment_definition,
            experiment_graph=experiment_graph,
            experiment_manager=self._experiment_manager,
            task_manager=self._task_manager,
            container_manager=self._container_manager,
            task_executor=self._task_executor,
            scheduler=self._scheduler,
        )
