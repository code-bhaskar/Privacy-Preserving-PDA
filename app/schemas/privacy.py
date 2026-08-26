from pydantic import BaseModel


class PrivacyPosture(BaseModel):
    technology: str
    status: str
    notes: str


class EncryptDemo(BaseModel):
    plaintext: str


class EncryptDemoResult(BaseModel):
    algorithm: str = "AES-256-GCM"
    ciphertext_b64: str
    roundtrip_ok: bool
