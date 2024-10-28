from motor.core import AgnosticClientSession

from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.persistence.mongodb_async_repository import MongoDbAsyncRepository
from eos.resource_allocation.entities.resource_request import (
    ResourceAllocationRequest,
    ResourceRequestAllocationStatus,
)


class ResourceRequestRepository(MongoDbAsyncRepository):
    def __init__(self, db_interface: AsyncMongoDbInterface):
        super().__init__("resource_requests", db_interface)

    async def get_requests_prioritized(
        self, status: ResourceRequestAllocationStatus, session: AgnosticClientSession | None = None
    ) -> list[dict]:
        return (
            await self._collection.find({"status": status.value}, session=session).sort("request.priority", 1).to_list()
        )

    async def get_existing_request(
        self, request: ResourceAllocationRequest, session: AgnosticClientSession | None = None
    ) -> dict:
        query = {
            "request.resources": [r.model_dump() for r in request.resources],
            "request.requester": request.requester,
            "status": {
                "$in": [
                    ResourceRequestAllocationStatus.PENDING.value,
                    ResourceRequestAllocationStatus.ALLOCATED.value,
                ]
            },
        }

        return await self._collection.find_one(query, session=session)

    async def clean_requests(self, session: AgnosticClientSession | None = None) -> None:
        await self._collection.delete_many(
            {
                "status": {
                    "$in": [
                        ResourceRequestAllocationStatus.COMPLETED.value,
                        ResourceRequestAllocationStatus.ABORTED.value,
                    ]
                }
            },
            session=session,
        )
