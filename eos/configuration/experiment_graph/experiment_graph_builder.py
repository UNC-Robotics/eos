import networkx as nx

from eos.configuration.entities.experiment import ExperimentConfig
from eos.configuration.spec_registries.task_spec_registry import (
    TaskSpecRegistry,
)
from eos.configuration.validation import validation_utils


class ExperimentGraphBuilder:
    """
    Builds an experiment graph from an experiment configuration and lab configurations.
    """

    def __init__(self, experiment_config: ExperimentConfig):
        self._experiment = experiment_config
        self._task_specs = TaskSpecRegistry()

    def build_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()

        self._add_begin_and_end_nodes(graph)
        self._add_task_nodes_and_edges(graph)
        self._add_container_nodes(graph)
        self._add_parameter_nodes(graph)
        self._connect_orphan_task_nodes(graph)
        self._remove_orphan_nodes(graph)

        return graph

    def _add_begin_and_end_nodes(self, graph: nx.DiGraph) -> None:
        graph.add_node("Begin", node_type="begin")
        graph.add_node("End", node_type="end")

        first_task = self._experiment.tasks[0].id
        last_task = self._experiment.tasks[-1].id
        graph.add_edge("Begin", first_task)
        graph.add_edge(last_task, "End")

    def _add_task_nodes_and_edges(self, graph: nx.DiGraph) -> None:
        for task in self._experiment.tasks:
            graph.add_node(task.id, node_type="task", task_config=task)
            for dep in task.dependencies:
                graph.add_edge(dep, task.id)

    @staticmethod
    def _connect_orphan_task_nodes(graph: nx.DiGraph) -> None:
        for node, node_data in list(graph.nodes(data=True)):
            if node_data["node_type"] == "task" and node not in ["Begin", "End"]:
                if graph.in_degree(node) == 0:
                    graph.add_edge("Begin", node)
                if graph.out_degree(node) == 0:
                    graph.add_edge(node, "End")

    def _add_container_nodes(self, graph: nx.DiGraph) -> None:
        container_mapping = {}
        used_containers = set()

        for task in self._experiment.tasks:
            for container_name, container_id in task.containers.items():
                # Determine the container ID for this task
                if container_id not in used_containers:
                    input_container_id = container_id
                else:
                    input_container_id = f"{container_id}_{task.id}"

                # If this container is used as output by a previous task, update the input_container_id
                if container_id in container_mapping:
                    previous_output_container_id = container_mapping[container_id]
                    input_container_id = previous_output_container_id

                # Add container node as input for the current task
                if input_container_id not in graph:
                    graph.add_node(input_container_id, node_type="container", container={container_name: container_id})
                graph.add_edge(input_container_id, task.id)

                # Add container node as output for the current task
                output_container_id = f"{container_id}_{task.id}"
                graph.add_node(output_container_id, node_type="container", container={container_name: container_id})
                graph.add_edge(task.id, output_container_id)

                # Update the container mapping to link the output of this task to the next task's input
                container_mapping[container_id] = output_container_id

                used_containers.add(container_id)

    def _add_parameter_nodes(self, graph: nx.DiGraph) -> None:
        for task in self._experiment.tasks:
            for param_name, param_value in task.parameters.items():
                if validation_utils.is_parameter_reference(param_value):
                    parameter_reference = param_value
                    producer_task_id, parameter_name = parameter_reference.split(".")
                    graph.add_node(parameter_reference, node_type="parameter")
                    graph.add_edge(parameter_reference, task.id, mapped_parameter=param_name)
                    graph.add_edge(producer_task_id, parameter_reference)

            # Add output parameters based on task specs
            task_spec = self._task_specs.get_spec_by_config(task)
            for param_name in task_spec.output_parameters:
                ref_param_name = f"{task.id}.{param_name}"
                graph.add_node(ref_param_name, node_type="parameter")
                graph.add_edge(task.id, ref_param_name)

    @staticmethod
    def _remove_orphan_nodes(graph: nx.DiGraph) -> None:
        orphan_nodes = [node for node in graph.nodes if graph.in_degree(node) == 0 and graph.out_degree(node) == 0]
        for node in orphan_nodes:
            graph.remove_node(node)
