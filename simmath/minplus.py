from simmath.LinearFunction import LinearFunction


def convolve(f: LinearFunction, g: LinearFunction) -> LinearFunction:
    """
    Min-plus convolution of two rate-latency service curves (concatenation of two servers):
    the rate is the minimum of both rates, the latencies add up.
    """
    return LinearFunction(min(f.m, g.m), min(f.c, g.c), f.a + g.a)
