# Backend Architecture & Security Audit Status

This document records the findings of the architectural and security audit of the PPDA backend, the remediation completed, and remaining items.

---

## 1. Authentication & Access Control (Resolved)

### Previous Vulnerabilities
- **Zero Authentication**: The original codebase contained no password storage, login endpoint, JWT verification, or bearer token handling.
- **Insecure Direct Object References (IDOR)**: Endpoints accepted `user_id` directly as client-supplied parameters in request bodies (`EventCreate`, `ReminderCreate`, `ConsentSet`, `CommandRequest`, `SummarizeRequest`) and query/path parameters (`GET /users/{user_id}`, `GET /consent/{user_id}`). An attacker could change an integer to read/modify any user's calendar, reminders, consent flags, or audit records.
- **Illusion of Consent Security**: Although consent enforcement (`consent_service.require`) existed, it evaluated permissions against the attacker-supplied `user_id`, providing zero actual isolation.

### Remediation Implemented
1. **Password Hashing**: Implemented direct `bcrypt` hashing (bypassing deprecated `passlib` compatibility issues) with explicit 72-byte truncation.
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

## 3. Audit Immutability & Migrations (In Progress / Next Phase)
- **Alembic Database Migrations**: Transition database lifecycle from `Base.metadata.create_all()` to versioned migrations with boot-time schema verification.
- **Append-Only Enforcement**: Install PostgreSQL/SQLite database triggers that strictly prohibit `UPDATE` and `DELETE` queries on `audit_logs`.
- **Cryptographic Hash Chain**: Add `prev_hash` and `integrity_hash` (SHA-256) chaining across sequential audit entries with verification endpoints (`GET /api/v1/audit/verify`).

---

## 4. On-Device Intent Classification Deployment (Next Phase)
- **Trained Model Serving**: Train the BiLSTM/EmbeddingBag architecture on the 8 PPDA intent classes and export to ONNX runtime format (~269 KB, <1 ms latency).
- **Assistant Integration**: Wire the ONNX model into `app/ml_models/model_inference.py` with rule-based fallback and occlusion saliency token attributions.
