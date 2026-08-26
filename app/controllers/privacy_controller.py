from sqlalchemy.orm import Session
from app.schemas.privacy import EncryptDemo
from app.services.privacy_service import privacy_service


class PrivacyController:
    def posture(self):
        return privacy_service.posture()

    def encrypt_demo(self, db: Session, payload: EncryptDemo):
        return privacy_service.encrypt_demo(db, payload.plaintext)


privacy_controller = PrivacyController()
