"""Fixed-point quantization. Secure aggregation requires integer arithmetic mod 2^32."""
import numpy as np

MODULUS_BITS = 32
QUANT_BITS = 20  # headroom: 2^20 * 1000 clients < 2^32


def quantize(vec: np.ndarray, clip: float) -> np.ndarray:
    """float32 vector in [-clip, clip] -> uint32."""
    v = np.clip(vec, -clip, clip)
    scale = (2 ** QUANT_BITS - 1) / (2 * clip)
    q = np.round((v + clip) * scale).astype(np.int64)
    return q.astype(np.uint32)


def dequantize_sum(q_sum: np.ndarray, clip: float, num_clients: int) -> np.ndarray:
    """Inverse of quantize applied to a SUM of num_clients vectors."""
    scale = (2 ** QUANT_BITS - 1) / (2 * clip)
    return (q_sum.astype(np.float64) / scale) - (num_clients * clip)
