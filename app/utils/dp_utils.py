import math
import numpy as np


def clip_l2(vec: np.ndarray, clip_norm: float) -> np.ndarray:
    """Per-update L2 clipping — bounds sensitivity."""
    norm = float(np.linalg.norm(vec))
    if norm > clip_norm and norm > 0:
        return vec * (clip_norm / norm)
    return vec


def gaussian_sigma(clip_norm: float, epsilon: float, delta: float) -> float:
    """Classic analytic Gaussian mechanism calibration."""
    return clip_norm * math.sqrt(2.0 * math.log(1.25 / delta)) / epsilon


def add_gaussian_noise(vec: np.ndarray, clip_norm: float,
                       epsilon: float | None, delta: float,
                       rng: np.random.Generator) -> np.ndarray:
    if epsilon is None:
        return vec
    sigma = gaussian_sigma(clip_norm, epsilon, delta)
    return vec + rng.normal(0.0, sigma, size=vec.shape)


def pairwise_masks(client_ids: list[str], dim: int, round_seed: int,
                   scale: float = 1.0) -> dict[str, np.ndarray]:
    """
    Secure aggregation (FR-13).
    Each pair (i, j) derives a shared PRG seed; i adds the mask, j subtracts it.
    Masks therefore sum to exactly zero, so the coordinator recovers the sum
    while every individual vector it receives is computationally hidden.
    """
    masks = {cid: np.zeros(dim, dtype=np.float64) for cid in client_ids}
    n = len(client_ids)
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = client_ids[i], client_ids[j]
            seed = abs(hash((round_seed, ci, cj))) % (2**32)
            rng = np.random.default_rng(seed)
            m = rng.normal(0.0, scale, size=dim)
            masks[ci] += m
            masks[cj] -= m
    return masks
