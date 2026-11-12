"""
Quick visual check of the min-plus / max-plus operations. Run with `python -m simmath.math_tester`.
"""
from simmath.LinearFunction import LinearFunction
from simmath.minplus import min
from simmath.utils import plot
f = LinearFunction(1, 0, 0)
g = LinearFunction(0.5, 0, -2)

plot(f, g, min(f,g))
print(min(f, g))