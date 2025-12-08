from sqlalchemy import String, Integer, ForeignKey, Index
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class AllocationRequestResourceModel(Base):
    """Database model for resources in an allocation request."""

    __tablename__ = "allocation_request_resources"

    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("allocation_requests.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    lab_name: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)

    __table_args__ = (Index("idx_alloc_req_resources_lab_name", "lab_name"),)
