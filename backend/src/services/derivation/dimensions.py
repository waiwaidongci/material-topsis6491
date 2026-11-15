"""Dimensional system: integer exponents over base dimensions.

The five base dimensions cover every quantity in the trade-off book, including
currency so that price-like quantities do not collapse into dimensionless
numbers.  A dimension is a tuple of five ints; the zero tuple means
dimensionless (e.g. the absorption coefficient alpha_w).
"""
from __future__ import annotations

# Order is part of the persisted JSON contract; never reorder.
DIMENSION_NAMES = ('length', 'mass', 'time', 'current', 'currency')
DIMENSIONLESS = (0, 0, 0, 0, 0)


def is_valid_dims(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == len(DIMENSION_NAMES)
        and all(isinstance(x, int) and not isinstance(x, bool) and abs(x) <= 12 for x in value)
    )


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(a, factor: int):
    return tuple(x * factor for x in a)


def same(a, b) -> bool:
    return tuple(a) == tuple(b)


def compatible(a, b) -> bool:
    """Addition/subtraction require identical dimensions."""
    return same(a, b)


def format_dims(value) -> str:
    parts = []
    for name, exp in zip(DIMENSION_NAMES, value):
        if exp:
            parts.append(name if exp == 1 else f'{name}^{exp}')
    return '·'.join(parts) if parts else 'dimensionless'
