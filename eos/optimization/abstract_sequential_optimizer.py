from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class AbstractSequentialOptimizer(ABC):
    """
    Abstract interface for a sequential optimizer.
    At a minimum, the optimizer should give new parameters to clients, receive results from clients, and
    report the best parameters found so far.
    """

    @abstractmethod
    def sample(self, num_protocol_runs: int = 1) -> pd.DataFrame:
        """
        Ask the optimizer for new experimental parameters. The experimental parameters are provided as a DataFrame,
        with one row per protocol run and one column per dynamic parameter in flat format (task_name/param_name).

        :param num_protocol_runs: The number of protocol runs for which to request new parameters.
        """

    @abstractmethod
    def report(self, inputs_df: pd.DataFrame, outputs_df: pd.DataFrame) -> None:
        """
        Report the results of protocols to the optimizer.

        :param inputs_df: A DataFrame with the input parameters for the protocols.
        :param outputs_df: A DataFrame with the output parameters for the protocols.
        """

    @abstractmethod
    def get_optimal_solutions(self) -> pd.DataFrame:
        """
        Get the set of best outputs found so far and the parameters that produced them.
        This is the Pareto front.

        :return: A dataframe with the best parameters and outputs found so far.
        """

    @abstractmethod
    def get_input_names(self) -> list[str]:
        """
        Get the names of the input parameters.

        :return: A list of the names of the input parameters.
        """

    @abstractmethod
    def get_output_names(self) -> list[str]:
        """
        Get the names of the output values.

        :return: A list of the names of the output parameter values.
        """

    @abstractmethod
    def get_num_samples_reported(self) -> int:
        """
        Get the number of samples reported to the optimizer.

        :return: The number of samples reported to the optimizer.
        """

    @classmethod
    def eos_param_schema(cls) -> list[dict[str, Any]]:
        """
        Describe optimizer-specific parameters so the web UI can render controls for them.

        Each entry is a dict with keys:
          key         - the constructor argument name (required)
          type        - "number", "text", "select", "checkbox" or "json" (required)
          label       - display name, defaults to the key
          description - help text shown under the control
          default     - value shown when the campaign does not override it
          min/max/step - bounds for "number"
          options     - list of allowed values for "select"
          runtime     - True if the parameter can be changed while a campaign is running

        :return: A list of parameter descriptors. Empty means no custom controls.
        """
        return []
