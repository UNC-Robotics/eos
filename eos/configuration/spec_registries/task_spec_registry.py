from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.configuration.spec_registries.spec_registry import SpecRegistry


class TaskSpecRegistry(SpecRegistry[TaskSpecConfig, TaskConfig]):
    """
    The task specification registry stores the specifications for all tasks that are available in EOS.
    """

    def __init__(
        self,
        task_specifications: dict[str, TaskSpecConfig],
        task_dirs_to_task_types: dict[str, str],
    ):
        updated_specs = self._update_output_resources(task_specifications)
        super().__init__(updated_specs, task_dirs_to_task_types)

    @staticmethod
    def _update_output_resources(specs: dict[str, TaskSpecConfig]) -> dict[str, TaskSpecConfig]:
        for spec in specs.values():
            if not spec.output_resources:
                spec.output_resources = spec.input_resources.copy()
        return specs
