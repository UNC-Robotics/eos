from dataclasses import dataclass
from typing import Any

import networkx as nx

from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import EosTaskGraphError, EosTaskValidationError
from eos.configuration.registries import TaskSpecRegistry
from eos.configuration.utils import (
    is_device_reference,
    is_fanin_parameter,
    is_parameter_reference,
    is_resource_reference,
)
from eos.logging.batch_error_logger import batch_error, raise_batched_errors


class ProtocolGraphBuilder:
    """
    Builds a protocol graph from a protocol configuration and lab configurations.
    """

    def __init__(self, protocol: ProtocolDef):
        self._protocol = protocol

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

        first_task = self._protocol.tasks[0].name
        last_task = self._protocol.tasks[-1].name
        graph.add_edge("Begin", first_task)
        graph.add_edge(last_task, "End")

    def _add_task_nodes_and_edges(self, graph: nx.DiGraph) -> None:
        for task in self._protocol.tasks:
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


class ProtocolGraph:
    """
    Represents the task graph of a protocol.
    """

    def __init__(self, protocol: ProtocolDef):
        self._protocol = protocol
        self._task_specs = TaskSpecRegistry()

        self._graph = ProtocolGraphBuilder(protocol).build_graph()

        self._task_subgraph = self._create_task_subgraph()

        if not nx.is_directed_acyclic_graph(self._task_subgraph):
            raise EosTaskGraphError(f"Task graph of protocol '{protocol.type}' contains cycles.")

        self._topologically_sorted_tasks = self._stable_topological_sort(self._task_subgraph)

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


class TaskReferenceOrderingValidator:
    """Validates that each task reference points to a transitive ancestor in the dependency DAG."""

    def __init__(self, protocol: ProtocolDef):
        self._protocol = protocol
        raw_graph = ProtocolGraphBuilder(protocol).build_graph()
        self._task_subgraph: nx.DiGraph = nx.DiGraph(
            nx.subgraph_view(raw_graph, filter_node=lambda n: raw_graph.nodes[n]["node_type"] == "task")
        )

        cycles = list(nx.simple_cycles(self._task_subgraph))
        if cycles:
            cycles_str = "; ".join(" -> ".join([*cycle, cycle[0]]) for cycle in cycles)
            raise EosTaskGraphError(f"Protocol '{protocol.type}' has dependency cycles: {cycles_str}")

        self._ancestors: dict[str, set[str]] = {
            task: nx.ancestors(self._task_subgraph, task) for task in self._task_subgraph.nodes
        }

    def validate(self) -> None:
        for task in self._protocol.tasks:
            self._validate_task_references(task)
        raise_batched_errors(root_exception_type=EosTaskValidationError)

    def ancestors_of(self, task_name: str) -> set[str]:
        return self._ancestors.get(task_name, set())

    def _validate_task_references(self, task: TaskDef) -> None:
        for parameter_name, parameter_value in task.parameters.items():
            if is_parameter_reference(parameter_value):
                ref_task_name = str(parameter_value).split(".")[0]
                self._check_ordering(task.name, ref_task_name, "parameter", parameter_name)
            elif is_fanin_parameter(parameter_value):
                for alternate in parameter_value:
                    self._check_ordering(task.name, alternate.split(".")[0], "parameter", parameter_name)

        for resource_name, resource_value in task.resources.items():
            if isinstance(resource_value, str) and is_resource_reference(resource_value):
                ref_task_name = resource_value.split(".")[0]
                self._check_ordering(task.name, ref_task_name, "resource", resource_name)

        for device_name, device_value in task.devices.items():
            if isinstance(device_value, str) and is_device_reference(device_value):
                ref_task_name = device_value.split(".")[0]
                self._check_ordering(task.name, ref_task_name, "device", device_name)

    def _check_ordering(self, task_name: str, ref_task_name: str, kind: str, slot_name: str) -> None:
        if ref_task_name == task_name:
            batch_error(
                f"{kind} '{slot_name}' in task '{task_name}' references itself.",
                EosTaskValidationError,
            )
            return

        # Dangling references are reported by TaskValidator.
        if ref_task_name not in self._task_subgraph.nodes:
            return

        if ref_task_name not in self._ancestors[task_name]:
            batch_error(
                f"{kind} '{slot_name}' in task '{task_name}' references task '{ref_task_name}' "
                f"which does not run before it. Add '{ref_task_name}' to the dependencies of "
                f"'{task_name}' (directly or transitively).",
                EosTaskValidationError,
            )
