"""RDP accountant for the Poisson-subsampled Gaussian mechanism.

Reference: Mironov et al. 2019 (RDP of the sampled Gaussian mechanism);
Balle et al. 2020 for the RDP -> (eps, delta) conversion.
"""
import math
from typing import List, Optional

DEFAULT_ORDERS = [1 + x / 10.0 for x in range(1, 100)] + list(range(12, 64))


def _log_add(a: float, b: float) -> float:
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    return max(a, b) + math.log1p(math.exp(-abs(a - b)))


def _log_comb(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _rdp_int_order(q: float, sigma: float, alpha: int) -> float:
    if q == 0 or sigma <= 0:
        return 0.0 if q == 0 else math.inf
    if q >= 1.0:
        return alpha / (2 * sigma ** 2)
    log_a = -math.inf
    for i in range(alpha + 1):
        term = (
            _log_comb(alpha, i)
            + i * math.log(q)
            + (alpha - i) * math.log1p(-q)
            + (i * i - i) / (2 * sigma ** 2)
        )
        log_a = _log_add(log_a, term)
    return float(log_a) / (alpha - 1)


def compute_rdp(q: float, sigma: float, steps: int,
                orders: Optional[List[float]] = None) -> List[float]:
    orders = orders or DEFAULT_ORDERS
    out = []
    for a in orders:
        ai = max(int(math.ceil(a)), 2)
        out.append(steps * _rdp_int_order(q, sigma, ai))
    return out


def rdp_to_dp(rdp: List[float], delta: float,
              orders: Optional[List[float]] = None) -> tuple[float, Optional[float]]:
    """Balle et al. 2020 conversion. Returns (epsilon, best_order)."""
    orders = orders or DEFAULT_ORDERS
    best_eps, best_ord = math.inf, None
    for r, a in zip(rdp, orders):
        if a <= 1:
            continue
        eps = r - (math.log(delta) + math.log(a)) / (a - 1) + math.log((a - 1) / a)
        if eps < best_eps:
            best_eps, best_ord = eps, a
    return best_eps, best_ord


def sigma_for_target_epsilon(q: float, steps: int, target_eps: float,
                             delta: float = 1e-5) -> float:
    """Binary-search the noise multiplier achieving target (eps, delta)."""
    lo, hi = 0.3, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        eps, _ = rdp_to_dp(compute_rdp(q, mid, steps), delta)
        if eps > target_eps:
            lo = mid
        else:
            hi = mid
    return hi


class PrivacyAccountant:
    """Client-level DP accounting across federated rounds."""

    def __init__(self, total_clients: int, clients_per_round: int, delta: float = 1e-5):
        self.q = min(1.0, clients_per_round / max(total_clients, 1))
        self.delta = delta
        self.steps = 0
        self.sigma: Optional[float] = None

    def step(self, noise_multiplier: float):
        self.sigma = noise_multiplier
        self.steps += 1

    def spent(self) -> dict:
        if not self.sigma or self.steps == 0:
            return {"epsilon": 0.0, "delta": self.delta, "rounds": self.steps,
                    "noise_multiplier": self.sigma, "note": "no DP noise applied"}
        eps, order = rdp_to_dp(compute_rdp(self.q, self.sigma, self.steps), self.delta)
        return {
            "epsilon": round(eps, 4),
            "delta": self.delta,
            "rounds": self.steps,
            "noise_multiplier": round(self.sigma, 4),
            "sampling_rate_q": round(self.q, 4),
            "optimal_rdp_order": order,
        }

    def reset(self):
        self.steps = 0
        self.sigma = None
