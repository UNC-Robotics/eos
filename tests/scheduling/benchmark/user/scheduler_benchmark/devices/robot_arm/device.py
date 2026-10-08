from eos import Device


class RobotArm(Device, type="robot_arm"):
    """Single shared robot arm for vial transfers between stations."""
