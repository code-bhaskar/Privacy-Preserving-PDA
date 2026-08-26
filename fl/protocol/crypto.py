"""X25519 key agreement, HKDF, ChaCha20 PRG, AES-GCM share sealing."""
import os

import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# ---------- Key agreement ----------

def gen_keypair() -> tuple[bytes, bytes]:
    """Returns (private_raw_32, public_raw_32)."""
    sk = X25519PrivateKey.generate()
    pk = sk.public_key()
    return (
        sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )


def agree(private_raw: bytes, peer_public_raw: bytes, info: bytes) -> bytes:
    """ECDH + HKDF -> 32-byte shared key."""
    sk = X25519PrivateKey.from_private_bytes(private_raw)
    pk = X25519PublicKey.from_public_bytes(peer_public_raw)
    shared = sk.exchange(pk)
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=info
    ).derive(shared)


# ---------- PRG ----------

def prg_uint32(seed32: bytes, num_elements: int) -> np.ndarray:
    """Expand a 32-byte seed into `num_elements` uniform uint32 via ChaCha20."""
    nbytes = num_elements * 4
    cipher = Cipher(algorithms.ChaCha20(seed32, b"\x00" * 16), mode=None)
    keystream = cipher.encryptor().update(b"\x00" * nbytes)
    return np.frombuffer(keystream, dtype="<u4").copy()


# ---------- Authenticated encryption for secret shares ----------

def seal(key32: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key32).encrypt(nonce, plaintext, None)


def unseal(key32: bytes, blob: bytes) -> bytes:
    return AESGCM(key32).decrypt(blob[:12], blob[12:], None)
