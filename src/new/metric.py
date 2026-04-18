import math
import re


_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def parse(text: str, pattern: str) -> float | None:
    rx = re.compile(pattern, re.MULTILINE)
    last = None
    for line in text.splitlines():
        m = rx.search(line)
        if m:
            num = _NUM.search(line[m.end():])
            if num:
                try:
                    last = float(num.group(0))
                except ValueError:
                    pass
    return last


def stats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(var)
