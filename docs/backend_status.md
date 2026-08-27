# Backend Architecture & Security Audit Status

This document records the findings of the architectural and security audit of the PPDA backend and the full remediation completed.

---

## 1. Authentication, Access Control & Data Protection (Resolved)

### Previous Vulnerabilities
- **Zero Authentication**: The original codebase contained no password storage, login endpoint, JWT verification, or bearer token handling.
- **Insecure Direct Object References (IDOR)**: Endpoints accepted `user_id` directly as client-supplied parameters in request bodies (`EventCreate`, `ReminderCreate`, `ConsentSet`, `CommandRequest`, `SummarizeRequest`) and query/path parameters (`GET /users/{user_id}`, `GET /consent/{user_id}`). An attacker could change an integer to read/modify any user's calendar, reminders, consent flags, or audit records.
- **Unencrypted Event Titles & Reminders**: While messages were encrypted, calendar event titles and reminder texts were previously stored in plaintext in the database and echoed into audit log reasons.
- **Missing Boot-Time Key Enforcement**: Hardcoded development secrets allowed the app to start even when `.env` was missing.
- **Missing Brute-Force Rate Limiting & Token Revocation**: No throttle on `/login` and no way to revoke a JWT.

### Remediation Implemented
1. **Password Hashing**: Implemented direct `bcrypt` hashing with explicit 72-byte truncation.
2. **JWT Authentication & Revocation**:
   - Added `POST /api/v1/login` issuing signed HS256 JSON Web Tokens with configurable expiration (`ACCESS_TOKEN_EXPIRE_MINUTES`).
   - Added `POST /api/v1/logout` with an in-memory revocation blocklist. Revoked tokens are immediately rejected with HTTP 401.
3. **Login Rate Limiting**: Added sliding-window rate limiting on `POST /api/v1/login` (5 failed attempts locks out for 5 minutes with HTTP 429).
4. **Identity Derivation & Schema Cleansing**: Stripped `user_id` from all client request bodies. User identity is derived exclusively from the verified token via `get_current_user`.
5. **Ownership & IDOR Defenses**:
   - Updates and deletions verify resource ownership against `current_user.id`.
   - Unauthorized access attempts return `404 Not Found` rather than `403 Forbidden` to prevent object existence enumeration.
   - Authentication errors return byte-identical failure messages (`"Incorrect email or password"`), backed by dummy hash timing mitigation.
6. **Data Encryption at Rest (AES-256-GCM)**:
   - Calendar event titles, reminder texts, and private message contents are encrypted at rest with AES-256-GCM using `user_id` as Authenticated Additional Data (AAD).
   - Sensitive titles and message contents are not written into `audit_logs.reason`.
7. **Strict Boot Enforcement**: `validate_security_keys()` verifies that `JWT_SECRET`/`JWT_SECRET_KEY` and a valid 32-byte base64 `AES_MASTER_KEY` are provided, refusing to boot otherwise.

---

## 2. Federated Learning Real-Stack Consolidation (Resolved)

### Previous Inconsistency
The repository previously had two competing FL implementations:
- `app/ml_models/federated_core.py`: An in-process `scikit-learn` simulator running in shared memory without real isolation or cryptography, mounted under `/api/v1/federated/*`.
- `fl/`: A genuine Bonawitz et al. secure aggregation implementation with isolated OS client processes, ChaCha20 PRG masking, Shamir secret sharing, and Rényi DP accounting, mounted under `/api/v1/fl/*`.

### Remediation Implemented
1. **Eliminated Mock Simulator**: Removed `app/ml_models/federated_core.py` and `app/utils/dp_utils.py`.
2. **Unified Routing**: Refactored `app/services/federated_service.py` to route all `/api/v1/federated/*` operations directly through the real `fl.server.coordinator.coordinator`.
3. **Honest Operational Refusal**: The API returns HTTP 400 with actionable instructions when no independent client processes are connected (`python -m fl.client.run --client-id <id>`), rather than faking execution.
4. **Privacy-Preserving Baseline**: Removed server-side centralized data pooling for baselines in `/federated/experiment`, preserving the core privacy guarantee that raw client data never touches the coordinator.

---

## 3. Audit Immutability & Migrations (Resolved)

### Remediation Implemented
1. **Alembic Database Migrations**:
   - Migrated from `Base.metadata.create_all()` to versioned Alembic migrations (`migrations/`).
   - `init_db()` checks that the database is migrated to the head revision (`check_db_migrated()`) and refuses to boot otherwise.
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
2. **ONNX Runtime Serving**: Wired `OnnxIntentClassifier` into `app/ml_models/model_inference.py` using single-threaded CPU execution (`active_backend() == "onnx"`).
3. **Explainability**: Integrated occlusion saliency attribution (`"occlusion saliency attribution (not SHAP/LIME)"`) measuring the marginal probability impact of each token.
4. **Graceful Fallback**: Maintained rule-based / TF-IDF classifier as an automatic fallback if the ONNX model is absent or fails.

---

## Verification & Test Results
- **Automated Tests**: 73 passing unit and integration tests (`pytest tests/`).
  - 10 tests: Audit hash chain integrity and trigger enforcement (`tests/test_audit_integrity.py`).
  - 41 tests: Authentication, JWT validation, logout revocation, rate limiting, data encryption at rest, and IDOR prevention (`tests/test_auth.py`).
  - 16 tests: Intent classification, ONNX latency, and explainability (`tests/test_intent_model.py`).
  - 6 tests: Bonawitz secure aggregation, Shamir secret sharing, and RDP accounting (`tests/test_secagg.py`).
