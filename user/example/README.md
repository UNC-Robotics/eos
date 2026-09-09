# Example EOS Package

This package runs two multiplication tasks and scores how close their final product is to 1024.
It needs no physical hardware.

- **Protocol**: `optimize_multiplication` selects a starting number and two factors.
- **Laboratory**: `multiplication_lab` contains multiplier and analyzer devices.
- **Tasks**: `Multiplication` computes a product. `Score Multiplication` returns `abs(product - 1024)` as its loss.

The protocol uses Beacon for optimization. See the
[custom Beacon guide](https://unc-robotics.github.io/eos/user-guide/custom_beacon.html)
for a complete grid-search replacement.
