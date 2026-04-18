import random
import time

random.seed(0)
arr = [random.random() for _ in range(10_000)]


def sort_me(xs):
    return sorted(xs)


t0 = time.perf_counter()
out = sort_me(arr)
t = time.perf_counter() - t0

assert out == sorted(arr)
print(f"avg_time_ms: {t * 1000:.3f}")
