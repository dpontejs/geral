"""What every daily game shares: a fixed order of puzzles per edition and the puzzle number."""

import random
from datetime import date


def shuffled[T](items: list[T], seed: str) -> list[T]:
    """`items` in a fixed pseudo-random order: the same for everyone, no repeats until the end."""
    order = list(items)
    random.Random(seed).shuffle(order)
    return order


def number_on(day: date, launch: date) -> int:
    """Puzzle number of `day`: #1 on the launch day."""
    return (day - launch).days + 1


def pick[T](order: list[T], number: int) -> T:
    return order[(number - 1) % len(order)]
