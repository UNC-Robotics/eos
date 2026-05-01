from eos.configuration.entities.task_def import (
    DeviceAssignmentDef,
    DeviceReferenceDef,
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
    ResourceReferenceDef,
    StaticResourceAssignmentDef,
    TaskDef,
)


class TestTaskDefDeviceNormalization:
    def test_bare_string_device_passthrough(self):
        t = TaskDef(name="t", type="T", devices={"arm": "robot_arm"})
        assert t.devices == {"arm": "robot_arm"}
        assert t.device_holds == {}

    def test_static_device_assignment_keeps_object_extracts_hold(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={"arm": DeviceAssignmentDef(lab_name="lab", name="robot_arm", hold=True)},
        )
        assert isinstance(t.devices["arm"], DeviceAssignmentDef)
        assert t.devices["arm"].lab_name == "lab"
        assert t.devices["arm"].name == "robot_arm"
        assert t.device_holds == {"arm": True}

    def test_static_device_assignment_no_hold_leaves_holds_empty(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={"arm": DeviceAssignmentDef(lab_name="lab", name="robot_arm")},
        )
        assert t.device_holds == {}

    def test_device_reference_reduces_to_string(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={"arm": DeviceReferenceDef(ref="prev.arm", hold=True)},
        )
        assert t.devices == {"arm": "prev.arm"}
        assert t.device_holds == {"arm": True}

    def test_device_reference_no_hold(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={"arm": DeviceReferenceDef(ref="prev.arm")},
        )
        assert t.devices == {"arm": "prev.arm"}
        assert t.device_holds == {}

    def test_dynamic_device_assignment_keeps_object_extracts_hold(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={"arm": DynamicDeviceAssignmentDef(device_type="robot_arm", hold=True)},
        )
        assert isinstance(t.devices["arm"], DynamicDeviceAssignmentDef)
        assert t.device_holds == {"arm": True}

    def test_dynamic_device_with_constraints_round_trips(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={
                "arm": DynamicDeviceAssignmentDef(
                    device_type="robot_arm",
                    allowed_labs=["lab_a", "lab_b"],
                ),
            },
        )
        d = t.devices["arm"]
        assert isinstance(d, DynamicDeviceAssignmentDef)
        assert d.allowed_labs == ["lab_a", "lab_b"]


class TestTaskDefResourceNormalization:
    def test_bare_string_resource_passthrough(self):
        t = TaskDef(name="t", type="T", resources={"beaker": "magnetic_mixer"})
        assert t.resources == {"beaker": "magnetic_mixer"}
        assert t.resource_holds == {}

    def test_static_resource_with_hold_reduces_to_string(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": StaticResourceAssignmentDef(name="magnetic_mixer", hold=True)},
        )
        assert t.resources == {"beaker": "magnetic_mixer"}
        assert t.resource_holds == {"beaker": True}

    def test_static_resource_from_dict(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": {"name": "magnetic_mixer", "hold": True}},
        )
        assert t.resources == {"beaker": "magnetic_mixer"}
        assert t.resource_holds == {"beaker": True}

    def test_static_resource_explicit_hold_false(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": StaticResourceAssignmentDef(name="magnetic_mixer", hold=False)},
        )
        assert t.resources == {"beaker": "magnetic_mixer"}
        assert t.resource_holds == {}

    def test_resource_reference_reduces_to_string(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": ResourceReferenceDef(ref="prev.beaker", hold=True)},
        )
        assert t.resources == {"beaker": "prev.beaker"}
        assert t.resource_holds == {"beaker": True}

    def test_resource_reference_no_hold(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": ResourceReferenceDef(ref="prev.beaker")},
        )
        assert t.resources == {"beaker": "prev.beaker"}
        assert t.resource_holds == {}

    def test_dynamic_resource_keeps_object_extracts_hold(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": DynamicResourceAssignmentDef(resource_type="beaker", hold=True)},
        )
        assert isinstance(t.resources["beaker"], DynamicResourceAssignmentDef)
        assert t.resource_holds == {"beaker": True}


class TestTaskDefMixedAssignments:
    def test_all_device_modes_extract_holds_independently(self):
        t = TaskDef(
            name="t",
            type="T",
            devices={
                "static_held": {"lab_name": "lab", "name": "d1", "hold": True},
                "static_plain": "d2",
                "ref_held": {"ref": "prev.d3", "hold": True},
                "dyn_held": {"allocation_type": "dynamic", "device_type": "x", "hold": True},
                "dyn_plain": {"allocation_type": "dynamic", "device_type": "y"},
            },
        )
        assert t.device_holds == {"static_held": True, "ref_held": True, "dyn_held": True}
        assert isinstance(t.devices["static_held"], DeviceAssignmentDef)
        assert t.devices["static_plain"] == "d2"
        assert t.devices["ref_held"] == "prev.d3"
        assert isinstance(t.devices["dyn_held"], DynamicDeviceAssignmentDef)
        assert isinstance(t.devices["dyn_plain"], DynamicDeviceAssignmentDef)

    def test_all_resource_modes_extract_holds_independently(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={
                "static_held": {"name": "r1", "hold": True},
                "static_plain": "r2",
                "ref_held": {"ref": "prev.r3", "hold": True},
                "dyn_held": {"allocation_type": "dynamic", "resource_type": "x", "hold": True},
                "dyn_plain": {"allocation_type": "dynamic", "resource_type": "y"},
            },
        )
        assert t.resource_holds == {"static_held": True, "ref_held": True, "dyn_held": True}
        assert t.resources["static_held"] == "r1"
        assert t.resources["static_plain"] == "r2"
        assert t.resources["ref_held"] == "prev.r3"
        assert isinstance(t.resources["dyn_held"], DynamicResourceAssignmentDef)
        assert isinstance(t.resources["dyn_plain"], DynamicResourceAssignmentDef)


class TestTaskDefDefaults:
    def test_empty_devices_and_resources(self):
        t = TaskDef(name="t", type="T")
        assert t.devices == {}
        assert t.resources == {}
        assert t.device_holds == {}
        assert t.resource_holds == {}

    def test_dependencies_and_parameters_pass_through(self):
        t = TaskDef(
            name="t",
            type="T",
            dependencies=["a", "b"],
            parameters={"speed": 60, "ref_param": "prev.out"},
        )
        assert t.dependencies == ["a", "b"]
        assert t.parameters == {"speed": 60, "ref_param": "prev.out"}

    def test_holds_excluded_from_serialization(self):
        t = TaskDef(
            name="t",
            type="T",
            resources={"beaker": StaticResourceAssignmentDef(name="b1", hold=True)},
        )
        dumped = t.model_dump()
        assert "resource_holds" not in dumped
        assert "device_holds" not in dumped
