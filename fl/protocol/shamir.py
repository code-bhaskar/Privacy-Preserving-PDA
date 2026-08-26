"""Shamir t-of-n secret sharing over GF(2^521 - 1)."""
import secrets
from typing import List, Tuple

PRIME = 2**521 - 1


def _eval_poly(coeffs: List[int], x: int, p: int) -> int:
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % p
    return acc


def split(secret_int: int, threshold: int, num_shares: int, p: int = PRIME) -> List[Tuple[int, int]]:
    if not 0 <= secret_int < p:
        raise ValueError("secret out of field range")
    if threshold > num_shares:
        raise ValueError("threshold > num_shares")
    coeffs = [secret_int] + [secrets.randbelow(p) for _ in range(threshold - 1)]
    return [(i, _eval_poly(coeffs, i, p)) for i in range(1, num_shares + 1)]


def reconstruct(shares: List[Tuple[int, int]], p: int = PRIME) -> int:
    """Lagrange interpolation at x=0."""
    total = 0
    for j, (xj, yj) in enumerate(shares):
        num, den = 1, 1
        for m, (xm, _) in enumerate(shares):
            if m == j:
                continue
            num = (num * (-xm)) % p
            den = (den * (xj - xm)) % p
        total = (total + yj * num * pow(den, -1, p)) % p
    return total


def bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def int_to_bytes(i: int, length: int = 32) -> bytes:
    return i.to_bytes(length, "big")
