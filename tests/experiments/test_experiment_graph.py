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

    def test_get_container_node(self, experiment_graph):
        container_node = experiment_graph.get_container_node("026749f8f40342b38157f9824ae2f512")
        assert container_node is not None
        assert container_node["node_type"] == "container"
        assert container_node["container"]["beaker"] == "026749f8f40342b38157f9824ae2f512"

    def test_get_task_dependencies(self, experiment_graph):
        dependencies = experiment_graph.get_task_dependencies("evaporation")
        assert dependencies == ["mixing"]

    def test_get_task_inputs(self, experiment_graph):
        inputs = experiment_graph.get_task_inputs("mixing")
        assert inputs.containers == ["026749f8f40342b38157f9824ae2f512"]

        inputs = experiment_graph.get_task_inputs("evaporation")
        assert inputs.parameters == ["mixing.mixing_time"]

    def test_get_task_outputs(self, experiment_graph):
        outputs = experiment_graph.get_task_outputs("mixing")
        assert outputs.containers == ["026749f8f40342b38157f9824ae2f512_mixing"]
        assert outputs.parameters == ["mixing.mixing_time"]
