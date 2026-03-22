from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DeviceIdentifier(BaseModel):
    """Identifies a specific device"""

    lab_name: str
    name: str


class DeviceAssignmentDef(BaseModel):
    """Specific device assignment"""

    lab_name: str
    name: str
    hold: bool = False


class DeviceReferenceDef(BaseModel):
    """Reference to another task's device, with optional hold."""

    ref: str
    hold: bool = False


class DynamicDeviceAssignmentDef(BaseModel):
    """Dynamic device requirements - selects one or more device by type."""

    allocation_type: Literal["dynamic"] = "dynamic"
    device_type: str
    hold: bool = False

    # Optional constraints to narrow down the selection
    allowed_labs: list[str] | None = None  # None = any lab
    allowed_devices: list[DeviceIdentifier] | None = None  # None = any device of the type

    @model_validator(mode="after")
    def validate_constraints(self) -> "DynamicDeviceAssignmentDef":
        return self


class ResourceReferenceDef(BaseModel):
    """Reference to another task's resource, with optional hold."""

    ref: str
    hold: bool = False


class DynamicResourceAssignmentDef(BaseModel):
    """Dynamic resource requirements - selects one or more resources by type."""

    allocation_type: Literal["dynamic"] = "dynamic"
    resource_type: str
    hold: bool = False

    @model_validator(mode="after")
    def validate_fields(self) -> "DynamicResourceAssignmentDef":
        if not self.resource_type or not self.resource_type.strip():
            raise ValueError("Dynamic resource request requires a non-empty 'resource_type'.")
        return self


class TaskDef(BaseModel):
    name: str
    type: str
    desc: str | None = None

    duration: int = 1  # seconds
    group: str | None = None

    devices: dict[str, str | DeviceAssignmentDef | DeviceReferenceDef | DynamicDeviceAssignmentDef] = Field(
        default_factory=dict
    )
    resources: dict[str, str | ResourceReferenceDef | DynamicResourceAssignmentDef] = Field(default_factory=dict)

    parameters: dict[str, Any] = Field(default_factory=dict)

    dependencies: list[str] = Field(default_factory=list)

    # Hold flags extracted during normalization (not serialized to YAML/JSON)
    device_holds: dict[str, bool] = Field(default_factory=dict, exclude=True)
    resource_holds: dict[str, bool] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def _normalize_and_extract_holds(self) -> "TaskDef":
        """
        Normalize reference defs to bare strings and extract hold flags.

        After this runs, devices/resources contain only the original types
        (str | DeviceAssignmentDef | DynamicDeviceAssignmentDef for devices,
         str | DynamicResourceAssignmentDef for resources).
        Hold flags are stored separately in device_holds/resource_holds.
        """
        for slot, dev in list(self.devices.items()):
            if isinstance(dev, DeviceReferenceDef):
                if dev.hold:
                    self.device_holds[slot] = True
                self.devices[slot] = dev.ref
            elif isinstance(dev, DeviceAssignmentDef | DynamicDeviceAssignmentDef):
                if dev.hold:
                    self.device_holds[slot] = True

        for slot, res in list(self.resources.items()):
            if isinstance(res, ResourceReferenceDef):
                if res.hold:
                    self.resource_holds[slot] = True
                self.resources[slot] = res.ref
            elif isinstance(res, DynamicResourceAssignmentDef):
                if res.hold:
                    self.resource_holds[slot] = True

        return self
