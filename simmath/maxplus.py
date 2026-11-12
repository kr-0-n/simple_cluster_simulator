from simmath.LinearFunction import LinearFunction


def multiply(*functions: LinearFunction) -> LinearFunction:
    """Max-plus multiplication, i.e. the pointwise sum of the functions (as a function with a = 0)."""
    m = sum(f.m for f in functions)
    c = sum(f.m * f.a + f.c for f in functions)
    return LinearFunction(m, c, 0)


def divide(f: LinearFunction, g: LinearFunction) -> LinearFunction:
    """Max-plus division, i.e. the pointwise difference f - g (as a function with a = 0)."""
    return LinearFunction(f.m - g.m, f.m * f.a + f.c - g.m * g.a - g.c, 0)
