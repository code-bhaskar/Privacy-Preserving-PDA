"""Client-level DP: clip the model delta, add DISTRIBUTED Gaussian noise.

Each of n clients adds N(0, (sigma*S/sqrt(n))^2). Secure aggregation sums them,
yielding total noise N(0, (sigma*S)^2) at the server -- i.e. central-DP strength
without a trusted server. This is why SecAgg and DP belong together.
"""
import numpy as np


def clip_update(delta: np.ndarray, clip_norm: float) -> tuple[np.ndarray, float]:
    l2 = float(np.linalg.norm(delta))
    factor = min(1.0, clip_norm / (l2 + 1e-12))
    return (delta * factor).astype(np.float32), l2


def add_distributed_noise(delta: np.ndarray, clip_norm: float,
                          noise_multiplier: float, num_clients: int,
                          rng: np.random.Generator) -> np.ndarray:
    if noise_multiplier <= 0:
        return delta
    std = noise_multiplier * clip_norm / np.sqrt(max(num_clients, 1))
    return (delta + rng.normal(0.0, std, size=delta.shape)).astype(np.float32)
