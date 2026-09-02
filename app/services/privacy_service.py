from sqlalchemy.orm import Session

from app.core.security import encrypt, decrypt
from app.schemas.privacy import PrivacyPosture, EncryptDemoResult
from app.services.audit_service import audit_service

# Mirrors PRD §9 — the single source of truth for what is real vs. designed.
POSTURE = [
    ("On-device inference", "IMPLEMENTED", "ONNX Runtime intent classifier + entity extraction + local extractive summarization, all in-process; 0 external calls"),
    ("Federated Learning", "IMPLEMENTED", "Real isolated client OS processes over HTTP training on disjoint non-IID SNIPS shards; no simulator, no shared memory"),
    ("Differential Privacy", "IMPLEMENTED", "Client-level L2 clipping + distributed Gaussian noise with Rényi DP accounting; measurable via /federated/experiment and the pipeline sweep"),
    ("Secure Aggregation", "IMPLEMENTED", "Bonawitz et al. CCS'17: X25519 ECDH, ChaCha20 PRG pairwise masking mod 2^32, Shamir (t,n) dropout recovery; server sees masked uint32 only"),
    ("AES-256-GCM at rest", "IMPLEMENTED", "Event titles, reminder texts and message content encrypted with AAD binding to user_id"),
    ("Append-only audit trail", "IMPLEMENTED", "SHA-256 hash chain + DB triggers rejecting UPDATE/DELETE; verified via /audit/verify"),
    ("Explainability", "IMPLEMENTED", "Occlusion saliency attribution on the ONNX intent classifier (not SHAP/LIME)"),
    ("Zero-trust auth", "IMPLEMENTED", "bcrypt + HS256 JWT, token revocation, login rate limiting, IDOR-immune 404s"),
    ("Poisoning robustness", "NOT_IMPLEMENTED", "Secure aggregation assumes an honest-but-curious server and honest clients; no Byzantine/sybil defence"),
    ("TLS 1.3", "DEPLOYMENT_REQUIREMENT", "Terminated at reverse proxy; not implemented in app code"),
    ("Third-party crypto audit", "NOT_DONE", "Protocol crypto is hand-rolled research-grade; not independently audited or production-hardened"),
    ("Hardware keystore / TPM", "ARCHITECTURE_ONLY", "Master key would be unwrapped from TPM in production"),
    ("Homomorphic Encryption", "FUTURE_WORK", "Deferred — computationally prohibitive for this prototype"),
    ("Intel SGX / ARM TrustZone", "FUTURE_WORK", "Deferred — requires specific hardware"),
    ("Private Information Retrieval", "FUTURE_WORK", "Deferred — not required for core assistant flows"),
]


class PrivacyService:
    def posture(self) -> list[PrivacyPosture]:
        return [PrivacyPosture(technology=t, status=s, notes=n) for t, s, n in POSTURE]

    def encrypt_demo(self, db: Session, plaintext: str) -> EncryptDemoResult:
        ct = encrypt(plaintext)
        ok = decrypt(ct) == plaintext
        audit_service.record(db, user_id=None, action="ENCRYPTION_DEMO",
                             data_type="demo", reason="AES-GCM round-trip demonstration")
        return EncryptDemoResult(ciphertext_b64=ct, roundtrip_ok=ok)


privacy_service = PrivacyService()
