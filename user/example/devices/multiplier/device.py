from eos import Device


class Multiplier(Device, type="multiplier"):
    """A device for multiplying two numbers."""

    def multiply(self, a: int, b: int) -> int:
        return a * b
