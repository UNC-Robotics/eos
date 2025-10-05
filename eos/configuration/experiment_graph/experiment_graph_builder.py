import networkx as nx

from eos.configuration.entities.experiment import ExperimentConfig


class ExperimentGraphBuilder:
    """
    Builds an experiment graph from an experiment configuration and lab configurations.
    """

    def __init__(self, experiment_config: ExperimentConfig):
        self._experiment = experiment_config

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
            graph.add_node(task.name, node_type="task", task_config=task)
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
