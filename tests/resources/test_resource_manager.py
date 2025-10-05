from tests.fixtures import *


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestResourceManager:
    @pytest.mark.asyncio
    async def test_set_resource_metadata(self, db, resource_manager):
        resource_name = "acf829f859e04fee80d54a1ee918555d"
        await resource_manager.set_meta(db, resource_name, {"substance": "water"})
        await resource_manager.set_meta(db, resource_name, {"temperature": "cold"})

        resource = await resource_manager.get_resource(db, resource_name)
        assert resource.meta == {"temperature": "cold"}

    @pytest.mark.asyncio
    async def test_add_resource_metadata(self, db, resource_manager):
        resource_name = "acf829f859e04fee80d54a1ee918555d"
        await resource_manager.add_meta(db, resource_name, {"substance": "water"})
        await resource_manager.add_meta(db, resource_name, {"temperature": "cold"})

        resource = await resource_manager.get_resource(db, resource_name)
        assert resource.meta == {
            "capacity": 500,
            "substance": "water",
            "temperature": "cold",
        }

    @pytest.mark.asyncio
    async def test_remove_resource_metadata(self, db, resource_manager):
        resource_name = "acf829f859e04fee80d54a1ee918555d"
        await resource_manager.add_meta(
            db, resource_name, {"substance": "water", "temperature": "cold", "color": "blue"}
        )
        await resource_manager.remove_meta(db, resource_name, ["color", "temperature"])

        resource = await resource_manager.get_resource(db, resource_name)
        assert resource.meta == {"capacity": 500, "substance": "water"}
