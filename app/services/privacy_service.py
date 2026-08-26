from sqlalchemy.orm import Session

from app.core.security import encrypt, decrypt
from app.schemas.privacy import PrivacyPosture, EncryptDemoResult
from app.services.audit_service import audit_service

# Mirrors PRD §9 — the single source of truth for what is real vs. designed.
POSTURE = [
    ("On-device inference", "IMPLEMENTED", "Intent, entity and summarization run in-process; no external calls"),
    ("Federated Learning", "IMPLEMENTED", "Simulated multi-client FedAvg over disjoint shards"),
    ("Differential Privacy", "IMPLEMENTED", "L2 clipping + Gaussian mechanism on model deltas; measurable via /federated/experiment"),
    ("Secure Aggregation", "IMPLEMENTED", "Pairwise additive masking; masks cancel in the sum"),
    ("AES-256-GCM at rest", "IMPLEMENTED", "Message content encrypted with AAD binding to user_id"),
    ("Append-only audit trail", "IMPLEMENTED", "Repository exposes create/read only"),
    ("Explainability (LIME-style)", "IMPLEMENTED", "Linear coefficient attribution on intent classifier"),
    ("TLS 1.3", "DEPLOYMENT_REQUIREMENT", "Terminated at reverse proxy; not implemented in app code"),
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
