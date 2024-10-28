import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.exceptions import EosConfigurationError
from eos.containers.container_manager import ContainerManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.entities.experiment import ExperimentStatus
from eos.experiments.experiment_manager import ExperimentManager
from asyncio import Lock as AsyncLock

from eos.logging.logger import log
from eos.orchestration.exceptions import EosExperimentTypeInUseError


class LoadingModule:
    """Responsible for loading/unloading entities such as labs, experiments, etc."""

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        device_manager: DeviceManager,
        container_manager: ContainerManager,
        experiment_manager: ExperimentManager,
    ):
        self._configuration_manager = configuration_manager
        self._device_manager = device_manager
        self._container_manager = container_manager
        self._experiment_manager = experiment_manager

        self._loading_lock = AsyncLock()

    async def load_labs(self, labs: set[str]) -> None:
        """
        Load one or more labs into the orchestrator.
        """
        self._configuration_manager.load_labs(labs)
        await self._device_manager.update_devices(loaded_labs=labs)
        await self._container_manager.update_containers(loaded_labs=labs)

    async def unload_labs(self, labs: set[str]) -> None:
        """
        Unload one or more labs from the orchestrator.
        """
        self._configuration_manager.unload_labs(labs)
        await self._device_manager.update_devices(unloaded_labs=labs)
        await self._container_manager.update_containers(unloaded_labs=labs)

    async def reload_labs(self, lab_types: set[str]) -> None:
        """
        Reload one or more labs in the orchestrator.
        """
        async with self._loading_lock:
            experiments_to_reload = set()
            for lab_type in lab_types:
                existing_experiments = await self._experiment_manager.get_experiments(
                    status=ExperimentStatus.RUNNING.value
                )

                for experiment in existing_experiments:
                    experiment_config = self._configuration_manager.experiments[experiment.type]
                    if lab_type in experiment_config.labs:
                        log.error(f"Cannot reload lab type '{lab_type}' as there are running experiments that use it.")
                        raise EosExperimentTypeInUseError

                # Determine experiments to reload for this lab type
                for experiment_type, experiment_config in self._configuration_manager.experiments.items():
                    if lab_type in experiment_config.labs:
                        experiments_to_reload.add(experiment_type)
            try:
                await self.unload_labs(lab_types)
                await self.load_labs(lab_types)
                self.load_experiments(experiments_to_reload)
            except EosConfigurationError:
                log.error(f"Error reloading labs: {traceback.format_exc()}")
                raise

    async def update_loaded_labs(self, lab_types: set[str]) -> None:
        """
        Update the loaded labs with new configurations.
        """
        async with self._loading_lock:
            currently_loaded = set(self._configuration_manager.labs.keys())

            if currently_loaded == lab_types:
                return

            to_unload = currently_loaded - lab_types
            to_load = lab_types - currently_loaded

            for lab_type in to_unload:
                existing_experiments = await self._experiment_manager.get_experiments(
                    status=ExperimentStatus.RUNNING.value
                )

                for experiment in existing_experiments:
                    experiment_config = self._configuration_manager.experiments[experiment.type]
                    if lab_type in experiment_config.labs:
                        log.error(f"Cannot unload lab type '{lab_type}' as there are running experiments that use it.")
                        raise EosExperimentTypeInUseError

            try:
                await self.unload_labs(to_unload)
                await self.load_labs(to_load)
            except EosConfigurationError:
                log.error(f"Error updating loaded labs: {traceback.format_exc()}")
                raise

    async def list_loaded_labs(self) -> dict[str, bool]:
        """
        Return a dictionary of lab types and a boolean indicating whether they are loaded.
        """
        return self._configuration_manager.get_lab_loaded_statuses()

    def load_experiments(self, experiment_types: set[str]) -> None:
        """
        Load one or more experiments into the orchestrator.
        """
        self._configuration_manager.load_experiments(experiment_types)

    def unload_experiments(self, experiment_types: set[str]) -> None:
        """
        Unload one or more experiments from the orchestrator.
        """
        self._configuration_manager.unload_experiments(experiment_types)

    async def reload_experiments(self, experiment_types: set[str]) -> None:
        """
        Reload one or more experiments in the orchestrator.
        """
        async with self._loading_lock:
            for experiment_type in experiment_types:
                existing_experiments = await self._experiment_manager.get_experiments(
                    status=ExperimentStatus.RUNNING.value, type=experiment_type
                )
                if existing_experiments:
                    log.error(
                        f"Cannot reload experiment type '{experiment_type}' as there are running experiments of this "
                        f"type."
                    )
                    raise EosExperimentTypeInUseError
            try:
                self.unload_experiments(experiment_types)
                self.load_experiments(experiment_types)
            except EosConfigurationError:
                log.error(f"Error reloading experiments: {traceback.format_exc()}")
                raise

    async def update_loaded_experiments(self, experiment_types: set[str]) -> None:
        """
        Update the loaded experiments with new configurations.
        """
        async with self._loading_lock:
            currently_loaded = set(self._configuration_manager.experiments.keys())

            if currently_loaded == experiment_types:
                return

            to_unload = currently_loaded - experiment_types
            to_load = experiment_types - currently_loaded

            for experiment_type in to_unload:
                existing_experiments = await self._experiment_manager.get_experiments(
                    status=ExperimentStatus.RUNNING.value, type=experiment_type
                )
                if existing_experiments:
                    log.error(
                        f"Cannot unload experiment type '{experiment_type}' as there are running experiments of this "
                        f"type."
                    )
                    raise EosExperimentTypeInUseError

            try:
                self.unload_experiments(to_unload)
                self.load_experiments(to_load)
            except EosConfigurationError:
                log.error(f"Error updating loaded experiments: {traceback.format_exc()}")
                raise

    async def get_loaded(self) -> dict[str, bool]:
        """
        Return a dictionary of experiment types and a boolean indicating whether they are loaded.
        """
        return self._configuration_manager.get_experiment_loaded_statuses()
