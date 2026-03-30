from tests.fixtures import *


@pytest.mark.parametrize("setup_lab_protocol", [("small_lab", "water_purification")], indirect=True)
class TestProtocolGraph:
    def test_get_graph(self, protocol_graph):
        graph = protocol_graph.get_graph()
        assert graph is not None

    def test_get_task_node(self, protocol_graph):
        task_node = protocol_graph.get_task_node("mixing")
        assert task_node is not None
        assert task_node["node_type"] == "task"
        assert task_node["task"].type == "Magnetic Mixing"

    def test_get_task_spec(self, protocol_graph):
        task_spec = protocol_graph.get_task_spec("mixing")
        assert task_spec is not None
        assert task_spec.type == "Magnetic Mixing"

    def test_get_task_dependencies(self, protocol_graph):
        dependencies = protocol_graph.get_task_dependencies("evaporation")
        assert dependencies == ["mixing"]
