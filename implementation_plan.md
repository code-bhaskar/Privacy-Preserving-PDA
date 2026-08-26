# PPDA Real Federated Learning & ONNX Integration Plan

This plan outlines the integration of the rigorous Federated Learning (FL) pipeline and ONNX on-device inference simulation based on the provided specifications and code blocks.

## Goal Description
Upgrade the PPDA prototype from a simulated FL loop to a genuine, cryptographic Federated Learning system with isolated client processes, real differential privacy (DP-SGD via Opacus/Accountant), and secure aggregation (Bonawitz et al.). We will also integrate ONNX runtime inference to prove the "on-device-class" capability of the intent model.

## Proposed Changes

### 1. ONNX Inference & Deployment
Integrate ONNX export and inference to validate the model's footprint.
#### [NEW] `fl/deploy/export_onnx.py`
- Script to export the trained PyTorch model to ONNX FP32 and INT8 formats.
#### [NEW] `app/ml_models/onnx_inference.py`
- Service to run inference using `onnxruntime` on the exported INT8 model.
#### [NEW] `fl/deploy/benchmark.py`
- Benchmark script to measure inference latency and size.

### 2. Cryptographic Secure Aggregation
Implement Bonawitz et al. secure aggregation so the server never sees unmasked client updates.
#### [NEW] `fl/protocol/shamir.py`
- Shamir t-of-n secret sharing for dropout recovery.
#### [NEW] `fl/protocol/crypto.py`
- X25519 ECDH, HKDF, ChaCha20 PRG, and AES-GCM for masks and key exchange.
#### [NEW] `fl/protocol/quantize.py`
- Fixed-point quantization for secure integer addition mod 2^32.
#### [NEW] `fl/protocol/secagg.py`
- Client and Server protocols for secure aggregation.

### 3. Differential Privacy
Implement client-level DP with a Rényi DP accountant.
#### [NEW] `fl/privacy/accountant.py`
- RDP accountant to compute true (ε, δ) bounds.
#### [NEW] `fl/privacy/dp_client.py`
- Distributed Gaussian noise addition and gradient clipping.

### 4. Data & Model
Use real SNIPS intent data and a plausible BiLSTM architecture.
#### [NEW] `fl/model/net.py`
- `IntentNet` model definition and state utilities.
#### [NEW] `fl/data/dataset.py`
- Dataset loader and hashing-trick tokenizer to avoid vocab leakage.
#### [NEW] `fl/data/prepare.py`
- Script to download SNIPS and partition it using Dirichlet (non-IID) distributions.

### 5. Server Coordinator & Routes
The backend endpoints orchestrating the FL round.
#### [NEW] `fl/server/coordinator.py`
- State machine for the FL phases (keys, shares, masked updates, unmasking).
#### [NEW] `fl/server/routes.py`
- FastAPI router exposing endpoints for clients to interact with the coordinator.
#### [MODIFY] `app/main.py`
- Include the `fl.server.routes.router` in the FastAPI app.

### 6. Isolated FL Client
The independent client process that holds private data and communicates over HTTP.
#### [NEW] `fl/client/agent.py`
- Client logic: handles cryptographic masking, local SGD, and DP.
#### [NEW] `fl/client/run.py`
- CLI entrypoint to spawn a client process.

### 7. Experiment Driver
#### [NEW] `fl/experiments/run_sweep.py`
- Script to automate the ε-sweep (1.0, 5.0, 10.0, ∞) and generate the accuracy curve.

## Verification Plan
### Automated & Manual Verification
1. Install new dependencies (`onnx`, `onnxruntime`, `cryptography`, `requests`).
2. Run `python -m fl.data.prepare --clients 5 --alpha 0.5` to download SNIPS.
3. Start the FastAPI backend server.
4. Spawn 5 independent client processes (`python -m fl.client.run --client-id <id>`).
5. Run the experiment sweep `python -m fl.experiments.run_sweep` and verify that a real accuracy curve vs ε is produced, proving the system trains effectively and securely.

## Open Questions
- Do you want me to also write the discrete Gaussian mechanism and Pytest suite you mentioned at the end of your prompt, or should we just stick to this core integration first?
