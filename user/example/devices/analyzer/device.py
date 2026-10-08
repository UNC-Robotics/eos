from eos import Device


class Analyzer(Device, type="analyzer"):
    """A device for analyzing the result of the multiplication of some numbers and computing a loss."""

    def analyze_result(self, number: int, product: int) -> int:
        return abs(product - 1024)
