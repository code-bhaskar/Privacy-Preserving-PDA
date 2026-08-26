"""Bonawitz et al. (CCS'17) practical secure aggregation.

Server learns SUM(x_u) and nothing else about any individual x_u.

Masking:  y_u = x_u + PRG(b_u) + sum_{v!=u} sign(u,v) * PRG(ECDH(s_u, s_v))  (mod 2^32)

Pairwise terms cancel in the sum because sign(u,v) = -sign(v,u).
Self-masks PRG(b_u) are removed via Shamir shares from surviving clients.
Dropped clients' pairwise masks are recovered via Shamir shares of their s secret key.
"""
import os
from typing import Dict, List

import numpy as np

from fl.protocol import crypto, shamir

SHARE_INT_BYTES = 66  # ceil(521 bits / 8) = 66


def pair_mask(my_s_sk: bytes, peer_s_pk: bytes, my_id: int, peer_id: int,
              d: int, round_id: int) -> np.ndarray:
    """Antisymmetric pairwise mask. Deterministic given the pair + round."""
    lo, hi = min(my_id, peer_id), max(my_id, peer_id)
    info = f"ppda-secagg-r{round_id}-{lo}-{hi}".encode()
    seed = crypto.agree(my_s_sk, peer_s_pk, info)
    m = crypto.prg_uint32(seed, d)
    return m if my_id < peer_id else (np.uint32(0) - m)  # mod 2^32 negation


def self_mask(b_seed: bytes, d: int) -> np.ndarray:
    return crypto.prg_uint32(b_seed, d)


# ---------------- Client side ----------------

class ClientSecAgg:
    def __init__(self, client_id: int, threshold: int, round_id: int):
        self.id = client_id
        self.threshold = threshold
        self.round_id = round_id
        self.c_sk, self.c_pk = crypto.gen_keypair()   # for sealing shares
        self.s_sk, self.s_pk = crypto.gen_keypair()   # for mask agreement
        self.b_seed = os.urandom(32)
        self.peer_pubkeys: Dict[int, Dict[str, bytes]] = {}
        self.received_shares: Dict[int, bytes] = {}
        self.own_share: bytes | None = None

    def public_keys(self) -> dict:
        return {"c_pk": self.c_pk.hex(), "s_pk": self.s_pk.hex()}

    def make_shares(self, peers: Dict[int, Dict[str, bytes]]) -> Dict[int, str]:
        """Shamir-split (s_sk, b_seed); seal each share for its recipient."""
        self.peer_pubkeys = peers
        ids = sorted(peers.keys())
        n = len(ids)

        s_shares = shamir.split(shamir.bytes_to_int(self.s_sk), self.threshold, n)
        b_shares = shamir.split(shamir.bytes_to_int(self.b_seed), self.threshold, n)

        out = {}
        self.own_share = None
        for idx, peer_id in enumerate(ids):
            payload = (
                s_shares[idx][0].to_bytes(4, "big")
                + s_shares[idx][1].to_bytes(SHARE_INT_BYTES, "big")
                + b_shares[idx][1].to_bytes(SHARE_INT_BYTES, "big")
            )
            if peer_id == self.id:
                # Keep our own share locally. Without it a client's own secret
                # can only be reconstructed from n-1 shares, which deadlocks
                # unmasking whenever threshold == n//2 + 1 and anyone drops.
                self.own_share = payload
                continue
            key = crypto.agree(
                self.c_sk, peers[peer_id]["c_pk"],
                f"ppda-share-r{self.round_id}".encode(),
            )
            out[peer_id] = crypto.seal(key, payload).hex()
        return out

    def store_shares(self, incoming: Dict[int, str]):
        self.received_shares = {int(k): bytes.fromhex(v) for k, v in incoming.items()}

    def mask_vector(self, x_quantized: np.ndarray, live_ids: List[int]) -> np.ndarray:
        d = len(x_quantized)
        y = x_quantized.copy()
        y += self_mask(self.b_seed, d)
        for pid in live_ids:
            if pid == self.id:
                continue
            y += pair_mask(
                self.s_sk, self.peer_pubkeys[pid]["s_pk"],
                self.id, pid, d, self.round_id,
            )
        return y  # uint32 wraparound == mod 2^32

    def _unpack(self, payload: bytes):
        return (
            int.from_bytes(payload[0:4], "big"),
            int.from_bytes(payload[4:4 + SHARE_INT_BYTES], "big"),
            int.from_bytes(payload[4 + SHARE_INT_BYTES:], "big"),
        )

    def reveal(self, survivors: List[int], dropped: List[int]) -> dict:
        """Open b-shares for survivors, s_sk-shares for dropouts. Never both."""
        b_out, s_out = {}, {}
        if self.own_share is not None and self.id in survivors:
            x_idx, _, b_share = self._unpack(self.own_share)
            b_out[self.id] = [x_idx, str(b_share)]
        for owner_id, blob in self.received_shares.items():
            key = crypto.agree(
                self.c_sk, self.peer_pubkeys[owner_id]["c_pk"],
                f"ppda-share-r{self.round_id}".encode(),
            )
            x_idx, s_share, b_share = self._unpack(crypto.unseal(key, blob))

            if owner_id in survivors:
                b_out[owner_id] = [x_idx, str(b_share)]
            elif owner_id in dropped:
                s_out[owner_id] = [x_idx, str(s_share)]
        return {"b_shares": b_out, "s_shares": s_out}


# ---------------- Server side ----------------

class ServerSecAgg:
    """The server NEVER holds a client's unmasked vector. Verify by reading this."""

    @staticmethod
    def aggregate(masked: Dict[int, np.ndarray],
                  b_share_pool: Dict[int, List],
                  s_share_pool: Dict[int, List],
                  pubkeys: Dict[int, Dict[str, bytes]],
                  live_ids: List[int],
                  dropped_ids: List[int],
                  threshold: int,
                  round_id: int) -> np.ndarray:
        d = len(next(iter(masked.values())))
        total = np.zeros(d, dtype=np.uint32)
        for v in masked.values():
            total += v

        # 1. Remove self-masks of surviving clients
        for owner_id, shares in b_share_pool.items():
            if len(shares) < threshold:
                raise RuntimeError(f"insufficient b-shares for client {owner_id}")
            b_int = shamir.reconstruct([(x, int(y)) for x, y in shares[:threshold]])
            total -= self_mask(shamir.int_to_bytes(b_int), d)

        # 2. Recover and remove dangling pairwise masks of dropped clients
        for dead_id, shares in s_share_pool.items():
            if len(shares) < threshold:
                raise RuntimeError(f"insufficient s-shares for dropped client {dead_id}")
            s_int = shamir.reconstruct([(x, int(y)) for x, y in shares[:threshold]])
            dead_sk = shamir.int_to_bytes(s_int)
            for live in live_ids:
                # Survivor `live` added sign(live, dead) * PRG(shared) which now
                # has no counterpart. pair_mask(dead -> live) is its negation,
                # so ADDING it cancels the dangling term.
                total += pair_mask(
                    dead_sk, pubkeys[live]["s_pk"], dead_id, live, d, round_id
                )
        return total
