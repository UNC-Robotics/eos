from dataclasses import dataclass
from typing import Any

import networkx as nx

from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.configuration.exceptions import EosTaskGraphError
from eos.configuration.experiment_graph.experiment_graph_builder import ExperimentGraphBuilder
from eos.configuration.spec_registries.task_spec_registry import TaskSpecRegistry


@dataclass
class TaskNodeIO:
    containers: list[str]
    parameters: list[str]


class ExperimentGraph:
    def __init__(self, experiment_config: ExperimentConfig):
        self._experiment_config = experiment_config
        self._task_specs = TaskSpecRegistry()

        self._graph = ExperimentGraphBuilder(experiment_config).build_graph()

        self._task_subgraph = self._create_task_subgraph()
        self._topologically_sorted_tasks = self._stable_topological_sort(self._task_subgraph)

        if not nx.is_directed_acyclic_graph(self._task_subgraph):
            raise EosTaskGraphError(f"Task graph of experiment '{experiment_config.type}' contains cycles.")

    def _create_task_subgraph(self) -> nx.Graph:
        return nx.subgraph_view(self._graph, filter_node=lambda n: self._graph.nodes[n]["node_type"] == "task")

    def get_graph(self) -> nx.DiGraph:
        return self._graph

    def get_task_graph(self) -> nx.DiGraph:
        return nx.DiGraph(self._task_subgraph)

    def get_tasks(self) -> list[str]:
        return list(self._task_subgraph.nodes)

    def get_topologically_sorted_tasks(self) -> list[str]:
        return self._topologically_sorted_tasks

    def get_task_node(self, task_id: str) -> dict[str, Any]:
        return self._graph.nodes[task_id]

    def get_task_config(self, task_id: str) -> TaskConfig:
        return self.get_task_node(task_id)["task_config"].model_copy(deep=True)

    def get_task_spec(self, task_id: str) -> TaskSpecConfig:
        return self._task_specs.get_spec_by_type(self.get_task_node(task_id)["task_config"].type)

    def get_task_dependencies(self, task_id: str) -> list[str]:
        return [pred for pred in self._graph.predecessors(task_id) if self._graph.nodes[pred]["node_type"] == "task"]

    def _get_node_by_type(self, task_id: str, node_type: str, direction: str) -> list[str]:
        if direction == "in":
            nodes = self._graph.predecessors(task_id)
        elif direction == "out":
            nodes = self._graph.successors(task_id)
        else:
            raise ValueError("direction must be 'in' or 'out'")

        return [node for node in nodes if self._graph.nodes[node]["node_type"] == node_type]

    def get_task_inputs(self, task_id: str) -> TaskNodeIO:
        return TaskNodeIO(
            containers=self._get_node_by_type(task_id, "container", "in"),
            parameters=self._get_node_by_type(task_id, "parameter", "in"),
        )

    def get_task_outputs(self, task_id: str) -> TaskNodeIO:
        return TaskNodeIO(
            containers=self._get_node_by_type(task_id, "container", "out"),
            parameters=self._get_node_by_type(task_id, "parameter", "out"),
        )

    def get_container_node(self, container_id: str) -> dict[str, Any]:
        return self._graph.nodes[container_id]

    @staticmethod
    def _stable_topological_sort(graph: nx.Graph) -> list[str]:
        nodes = sorted(graph.nodes())
        return list(nx.topological_sort(nx.DiGraph((u, v) for u, v in graph.edges() if u in nodes and v in nodes)))
