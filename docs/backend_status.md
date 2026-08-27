# Backend Architecture & Security Audit Status

This document records the findings of the architectural and security audit of the PPDA backend and the full remediation completed.

---

## 1. Authentication & Access Control (Resolved)

### Previous Vulnerabilities
- **Zero Authentication**: The original codebase contained no password storage, login endpoint, JWT verification, or bearer token handling.
- **Insecure Direct Object References (IDOR)**: Endpoints accepted `user_id` directly as client-supplied parameters in request bodies (`EventCreate`, `ReminderCreate`, `ConsentSet`, `CommandRequest`, `SummarizeRequest`) and query/path parameters (`GET /users/{user_id}`, `GET /consent/{user_id}`). An attacker could change an integer to read/modify any user's calendar, reminders, consent flags, or audit records.
- **Illusion of Consent Security**: Although consent enforcement (`consent_service.require`) existed, it evaluated permissions against the attacker-supplied `user_id`, providing zero actual isolation.

### Remediation Implemented
1. **Password Hashing**: Implemented direct `bcrypt` hashing with explicit 72-byte truncation.
2. **JWT Authentication**: Added `POST /api/v1/login` issuing signed HS256 JSON Web Tokens with configurable expiration (`ACCESS_TOKEN_EXPIRE_MINUTES`).
3. **Identity Derivation**: `get_current_user` extracts and verifies bearer tokens via OAuth2, resolving the authenticated `User` from the database on every request.
4. **Schema Cleansing**: Stripped `user_id` from all client request bodies. User identity is derived exclusively from the verified token.
5. **Ownership & IDOR Defenses**:
   - Updates and deletions verify resource ownership against `current_user.id`.
   - Unauthorized access attempts return `404 Not Found` rather than `403 Forbidden` to prevent object existence enumeration.
   - Authentication errors return byte-identical failure messages (`"Incorrect email or password"`) for both unknown emails and incorrect passwords to prevent account enumeration, backed by dummy hash timing mitigation.
6. **Secrets Management**: Untracked `.env` from git history and provided `.env.example`.

---

## 2. Federated Learning Real-Stack Consolidation (Resolved)

### Previous Inconsistency
The repository previously had two competing FL implementations:
- `app/ml_models/federated_core.py`: An in-process `scikit-learn` simulator running in shared memory without real isolation or cryptography, mounted under `/api/v1/federated/*`.
- `fl/`: A genuine Bonawitz et al. secure aggregation implementation with isolated OS client processes, ChaCha20 PRG masking, Shamir secret sharing, and Rényi DP accounting, mounted under `/api/v1/fl/*`.

### Remediation Implemented
1. **Eliminated Mock Simulator**: Removed `app/ml_models/federated_core.py`.
2. **Unified Routing**: Refactored `app/services/federated_service.py` to route all `/api/v1/federated/*` operations directly through the real `fl.server.coordinator.coordinator`.
3. **Honest Operational Refusal**: The API returns HTTP 400 with actionable instructions when no independent client processes are connected (`python -m fl.client.run --client-id <id>`), rather than faking execution.
4. **Privacy-Preserving Baseline**: Removed server-side centralized data pooling for baselines in `/federated/experiment`, preserving the core privacy guarantee that raw client data never touches the coordinator.

---

## 3. Audit Immutability & Migrations (Resolved)

### Remediation Implemented
1. **Alembic Database Migrations**:
   - Migrated from `Base.metadata.create_all()` to versioned Alembic migrations (`migrations/`).
   - `init_db()` checks that the database is migrated to the head revision and refuses to boot otherwise to prevent unmanaged or partially configured schemas.
2. **Append-Only Database Triggers**:
   - Migration `b1a7c3d9e042_audit_append_only_trigger.py` adds triggers for both PostgreSQL and SQLite prohibiting `UPDATE` and `DELETE` queries on `audit_logs`.
3. **Cryptographic Hash Chain**:
   - Added `prev_hash` and `integrity_hash` (SHA-256) columns to `AuditLog`.
   - Sequential audit logs link each entry to its predecessor's hash.
   - Added `GET /api/v1/audit/verify` which validates the entire hash chain from the genesis entry, immediately detecting any unauthorized database tampering or deletions.

---

## 4. On-Device Intent Classification Deployment (Resolved)

### Remediation Implemented
1. **Model Alignment**: Trained the `IntentNet` architecture on the 8 PPDA assistant intents (`SCHEDULE_EVENT`, `CREATE_REMINDER`, `GET_EVENTS`, `GET_REMINDERS`, `DELETE_EVENT`, `DELETE_REMINDER`, `SUMMARIZE_MESSAGES`, `GREETING`) and exported to ONNX format (`deployed_models/intent_model.onnx`).
2. **ONNX Runtime Serving**: Wired `OnnxIntentClassifier` into `app/ml_models/model_inference.py` using single-threaded CPU execution to represent on-device mobile hardware.
3. **Explainability**: Integrated occlusion saliency attribution (`"occlusion saliency attribution (not SHAP/LIME)"`) measuring the marginal probability impact of each token.
4. **Graceful Fallback**: Maintained rule-based / TF-IDF classifier as an automatic fallback if the ONNX model is absent or fails.

---

## Verification & Test Results
- **Automated Tests**: 69 passing unit and integration tests (`pytest tests/`).
  - 10 tests: Audit hash chain integrity and trigger enforcement (`tests/test_audit_integrity.py`).
  - 37 tests: Authentication, JWT validation, and IDOR prevention (`tests/test_auth.py`).
  - 16 tests: Intent classification, ONNX latency, and explainability (`tests/test_intent_model.py`).
  - 6 tests: Bonawitz secure aggregation, Shamir secret sharing, and RDP accounting (`tests/test_secagg.py`).
