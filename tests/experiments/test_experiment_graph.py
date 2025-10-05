from tests.fixtures import *


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestExperimentGraph:
    def test_get_graph(self, experiment_graph):
        graph = experiment_graph.get_graph()
        assert graph is not None

    def test_get_task_node(self, experiment_graph):
        task_node = experiment_graph.get_task_node("mixing")
        assert task_node is not None
        assert task_node["node_type"] == "task"
        assert task_node["task_config"].type == "Magnetic Mixing"

    def test_get_task_spec(self, experiment_graph):
        task_spec = experiment_graph.get_task_spec("mixing")
        assert task_spec is not None
        assert task_spec.type == "Magnetic Mixing"

    def test_get_task_dependencies(self, experiment_graph):
        dependencies = experiment_graph.get_task_dependencies("evaporation")
        assert dependencies == ["mixing"]
