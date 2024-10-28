from tests.fixtures import *


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestContainerManager:
    @pytest.mark.asyncio
    async def test_set_container_location(self, container_manager):
        container_id = "acf829f859e04fee80d54a1ee918555d"
        await container_manager.set_location(container_id, "new_location")

        container = await container_manager.get_container(container_id)
        assert container.location == "new_location"

    @pytest.mark.asyncio
    async def test_set_container_lab(self, container_manager):
        container_id = "acf829f859e04fee80d54a1ee918555d"
        await container_manager.set_lab(container_id, "new_lab")

        container = await container_manager.get_container(container_id)
        assert container.lab == "new_lab"

    @pytest.mark.asyncio
    async def test_set_container_metadata(self, container_manager):
        container_id = "acf829f859e04fee80d54a1ee918555d"
        await container_manager.set_metadata(container_id, {"substance": "water"})
        await container_manager.set_metadata(container_id, {"temperature": "cold"})

        container = await container_manager.get_container(container_id)
        assert container.metadata == {"temperature": "cold"}

    @pytest.mark.asyncio
    async def test_add_container_metadata(self, container_manager):
        container_id = "acf829f859e04fee80d54a1ee918555d"
        await container_manager.add_metadata(container_id, {"substance": "water"})
        await container_manager.add_metadata(container_id, {"temperature": "cold"})

        container = await container_manager.get_container(container_id)
        assert container.metadata == {
            "capacity": 500,
            "substance": "water",
            "temperature": "cold",
        }

    @pytest.mark.asyncio
    async def test_remove_container_metadata(self, container_manager):
        container_id = "acf829f859e04fee80d54a1ee918555d"
        await container_manager.add_metadata(
            container_id, {"substance": "water", "temperature": "cold", "color": "blue"}
        )
        await container_manager.remove_metadata(container_id, ["color", "temperature"])

        container = await container_manager.get_container(container_id)
        assert container.metadata == {"capacity": 500, "substance": "water"}
