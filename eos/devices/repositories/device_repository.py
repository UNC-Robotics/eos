from typing import Any

from motor.core import AgnosticClientSession
from pymongo import UpdateOne
from pymongo.results import DeleteResult, BulkWriteResult

from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.persistence.mongodb_async_repository import MongoDbAsyncRepository


class DeviceRepository(MongoDbAsyncRepository):
    def __init__(self, db_interface: AsyncMongoDbInterface):
        super().__init__("devices", db_interface)

    async def initialize(self) -> None:
        await self.create_indices([("lab_id", 1), ("id", 1)], unique=True)

    async def delete_devices_by_lab_ids(
        self, lab_ids: list[str], session: AgnosticClientSession | None = None
    ) -> DeleteResult:
        """
        Delete all devices associated with the given lab IDs in a single operation.

        :param lab_ids: List of lab_ids for which to delete devices.
        :param session: The database client session.
        :return: The result of the delete operation.
        """
        return await self._collection.delete_many({"lab_id": {"$in": lab_ids}}, session=session)

    async def get_devices_by_lab_ids(
        self, lab_ids: list[str], session: AgnosticClientSession | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Get all devices associated with the given lab IDs in a single operation.

        :param lab_ids: List of lab_ids for which to fetch devices.
        :param session: The database client session.
        :return: A dictionary with lab_ids as keys and lists of devices as values.
        """
        cursor = self._collection.find({"lab_id": {"$in": lab_ids}}, session=session)
        devices = await cursor.to_list(length=None)

        # Group devices by lab_id
        devices_by_lab = {lab_id: [] for lab_id in lab_ids}
        for device in devices:
            devices_by_lab[device["lab_id"]].append(device)

        return devices_by_lab

    async def bulk_upsert(
        self, devices: list[dict[str, Any]], session: AgnosticClientSession | None = None
    ) -> BulkWriteResult:
        """
        Perform a bulk upsert operation for multiple devices.

        :param devices: List of device dictionaries to upsert.
        :param session: The database client session.
        :return: The result of the bulk write operation.
        """
        operations = [
            UpdateOne({"lab_id": device["lab_id"], "id": device["id"]}, {"$set": device}, upsert=True)
            for device in devices
        ]
        return await self._collection.bulk_write(operations, session=session)
