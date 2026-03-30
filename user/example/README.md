# Example EOS Package
This is a very simple EOS package that implements a protocol for finding the smallest number that when multiplied by
two factors is as close as possible to 1024.

## Protocols
The package contains the **optimize_multiplication** protocol which works as explained above.

## Laboratories
The package defines a very basic laboratory containing a "multiplier" and an "analyzer" device.

## Devices
1. **Multiplier**: Provides a function for multiplying two numbers.
2. **Analyzer**: Provides a function for producing a score on how close we are to the objective of the protocol.

## Tasks
1. **Multiply**: Multiplies two numbers using the multiplier device.
2. **Score Multiplication**: Scores the multiplication using the analyzer device.
