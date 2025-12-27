from dataclasses import dataclass
from typing import Any

import networkx as nx

from eos.configuration.entities.experiment_def import ExperimentDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import EosTaskGraphError
from eos.configuration.registries import TaskSpecRegistry


class ExperimentGraphBuilder:
    """
    Builds an experiment graph from an experiment configuration and lab configurations.
    """

    def __init__(self, experiment: ExperimentDef):
        self._experiment = experiment

    def build_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()

        self._add_begin_and_end_nodes(graph)
        self._add_task_nodes_and_edges(graph)
        self._connect_orphan_task_nodes(graph)
        self._remove_orphan_nodes(graph)

        return graph

    def _add_begin_and_end_nodes(self, graph: nx.DiGraph) -> None:
        graph.add_node("Begin", node_type="begin")
        graph.add_node("End", node_type="end")

        first_task = self._experiment.tasks[0].name
        last_task = self._experiment.tasks[-1].name
        graph.add_edge("Begin", first_task)
        graph.add_edge(last_task, "End")

    def _add_task_nodes_and_edges(self, graph: nx.DiGraph) -> None:
        for task in self._experiment.tasks:
            graph.add_node(task.name, node_type="task", task=task)
            for dep in task.dependencies:
                graph.add_edge(dep, task.name)

    @staticmethod
    def _connect_orphan_task_nodes(graph: nx.DiGraph) -> None:
        for node, node_data in list(graph.nodes(data=True)):
            if node_data["node_type"] == "task" and node not in ["Begin", "End"]:
                if graph.in_degree(node) == 0:
                    graph.add_edge("Begin", node)
                if graph.out_degree(node) == 0:
                    graph.add_edge(node, "End")

    @staticmethod
    def _remove_orphan_nodes(graph: nx.DiGraph) -> None:
        orphan_nodes = [node for node in graph.nodes if graph.in_degree(node) == 0 and graph.out_degree(node) == 0]
        for node in orphan_nodes:
            graph.remove_node(node)


@dataclass
class TaskNodeIO:
    resources: list[str]
    parameters: list[str]


class ExperimentGraph:
    """
    Represents the task graph of an experiment.
    """

    def __init__(self, experiment: ExperimentDef):
        self._experiment = experiment
        self._task_specs = TaskSpecRegistry()

        self._graph = ExperimentGraphBuilder(experiment).build_graph()

        self._task_subgraph = self._create_task_subgraph()
        self._topologically_sorted_tasks = self._stable_topological_sort(self._task_subgraph)

        if not nx.is_directed_acyclic_graph(self._task_subgraph):
            raise EosTaskGraphError(f"Task graph of experiment '{experiment.type}' contains cycles.")

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

    def get_task_node(self, task_name: str) -> dict[str, Any]:
        return self._graph.nodes[task_name]

    def get_task(self, task_name: str) -> TaskDef:
        return self.get_task_node(task_name)["task"].model_copy(deep=True)

    def get_task_spec(self, task_name: str) -> TaskSpecDef:
        return self._task_specs.get_spec_by_type(self.get_task_node(task_name)["task"].type)

    def get_task_dependencies(self, task_name: str) -> list[str]:
        return [pred for pred in self._graph.predecessors(task_name) if self._graph.nodes[pred]["node_type"] == "task"]

    @staticmethod
    def _stable_topological_sort(graph: nx.Graph) -> list[str]:
        nodes = sorted(graph.nodes())

        dg = nx.DiGraph()
        dg.add_nodes_from(nodes)
        dg.add_edges_from(graph.edges())

        return list(nx.topological_sort(dg))
