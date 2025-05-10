from eos.configuration.eos_config import SchedulerType
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.scheduling.cpsat_scheduler import CpSatScheduler


class SchedulerFactory:
    @staticmethod
    def create_scheduler(scheduler_type: SchedulerType) -> AbstractScheduler:
        """
        Create and return an instance of a scheduler based on the provided scheduler type.

        :param scheduler_type: The scheduler type from the configuration.
        :return: An instance of a scheduler implementing AbstractScheduler.
        :raises ValueError: If the scheduler type is unsupported.
        """
        if scheduler_type == SchedulerType.GREEDY:
            return GreedyScheduler()
        if scheduler_type == SchedulerType.CPSAT:
            return CpSatScheduler()

        raise ValueError(f"Unsupported scheduler type '{scheduler_type.value}'")
