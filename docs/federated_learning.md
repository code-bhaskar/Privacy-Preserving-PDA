# Federated Learning in PPDA — What Is Actually Implemented

All numbers below were produced by running the code in this repository.
Reproduce with `scripts/run_fl_demo.sh`.

---

## 1. Honest scope statement

| Category | Listed in the original problem statement | Implemented here |
|---|---|---|
| **Dataset** | SNIPS, ATIS, GLUE, SQuAD, LEAF, MobiAct | **SNIPS only** (13,784 utterances, 7 intents), split LEAF-*style* via Dirichlet(α=0.5) |
| **FL framework** | TensorFlow Federated, Flower, PyTorch FedAvg | **Custom PyTorch FedAvg** over real HTTP + independent OS processes |
| **On-device runtime** | TFLite, ONNX Runtime Mobile, Core ML | **ONNX Runtime** (CPUExecutionProvider, single thread) |
| **Secure aggregation** | required | **Bonawitz et al. CCS'17**: X25519 ECDH, ChaCha20 PRG, Shamir t-of-n |
| **Differential privacy** | required | Client-level clipping + **distributed Gaussian**, **RDP accountant** |
| **HE / SGX / TrustZone / PIR** | listed | **Not built** — architecture notes only |

Nothing in this table is aspirational. If it says implemented, it runs.

---

## 2. Why "real" and not a simulation

| Property | Evidence |
|---|---|
| Clients are isolated | 6 separate OS processes (`python -m fl.client.run --client-id k`), each reading only `fl_data/client_k/train.jsonl` |
| Data never leaves the client | The only payload posted to the server is `vector_hex`, a masked `uint32` array |
| Training is genuine | Real SGD on real SNIPS text; local loss falls from ~1.9 to ~0.15 |
| Server cannot see an update | `ServerSecAgg.aggregate()` only ever touches `uint32` sums; no code path reaches a plaintext delta |
| Privacy accounting is genuine | RDP composition over the rounds actually executed, not a constant in a diagram |
| Network is real | HTTP; point `--server-url` at another host and it works unchanged |

The clients are processes rather than phones. That is a deployment detail, not an
algorithmic one, and it is stated plainly rather than dressed up.

---

## 3. Protocol

Six-phase state machine per round (`fl/server/coordinator.py`):

```
ADVERTISE_KEYS -> SHARE_KEYS -> COLLECT -> UNMASK -> AGGREGATING -> DONE
```

Masking, per client `u` over `d` model parameters:

```
y_u = x_u + PRG(b_u) + sum_{v != u} sign(u,v) * PRG(ECDH(s_u, s_v))   (mod 2^32)
```

* `sign(u,v) = -sign(v,u)`, so every pairwise term cancels in `sum_u y_u`.
* Self-masks `PRG(b_u)` are removed via Shamir shares contributed by survivors.
* A **dropped** client's dangling pairwise masks are recovered from Shamir shares
  of its `s` secret key. Shares of `b` and of `s` are *never* opened for the same
  client — that is what stops the server unmasking anyone.

Masks are uniform over `uint32`, so adding one to a quantized value is a
one-time pad: the server learns nothing about an individual update in the
information-theoretic sense.

### Two protocol bugs found and fixed while building this

1. **Dropout sign error.** Recovering a dropped client's mask requires *adding*
   `pair_mask(dead -> live)` (it is the negation of the survivor's dangling
   term), not subtracting it. Caught by `test_server_aggregate_with_dropout`.
2. **Share-count deadlock.** Each client now retains its own Shamir share.
   Without it, an owner's secret is recoverable only from `n-1` shares, which
   deadlocks unmasking whenever `threshold = n//2 + 1` and anyone drops.

---

## 4. Differential privacy

* **Granularity:** client-level (one client's entire contribution is protected).
* **Clipping:** L2 norm of the model delta, `clip_norm = 20`.
* **Noise:** each of `n` sampled clients adds `N(0, (sigma*S/sqrt(n))^2)`.
  Secure aggregation sums them into `N(0, (sigma*S)^2)` at the server, giving
  central-DP strength *without* a trusted server. This is why SecAgg and DP
  belong together here.
* **Accounting:** RDP for the Poisson-subsampled Gaussian mechanism
  (Mironov 2019), converted to `(eps, delta)` via Balle 2020.
  `sigma` is binary-searched to hit the target `eps` over the planned rounds.

Sampling matters: with 6 registered clients and 3 sampled per round, `q = 0.5`,
and hitting `eps = 1` over 20 rounds needs `sigma = 9.28`.

---

## 5. Measured results

Configuration: 6 clients registered, 3 sampled/round, 20 rounds, 1 local epoch,
`lr = 0.5`, `clip_norm = 20`, `delta = 1e-5`, SNIPS held-out test set (2,067 utterances).

| Target eps | delta | Noise multiplier | Final test accuracy | Uplink/client/round |
|---:|---:|---:|---:|---:|
| ∞ (no DP) | – | 0.00 | **0.9555** | 272,412 B |
| 10 | 1e-5 | 1.41 | 0.3164 | 272,412 B |
| 5 | 1e-5 | 2.37 | 0.2022 | 272,412 B |
| 1 | 1e-5 | 9.28 | 0.1722 | 272,412 B |

Chance is 1/7 ≈ 0.143. Accuracy is monotone in `eps`, which is the expected
privacy–utility trade-off. Chart: `results/accuracy_vs_epsilon.png`;
table: `results/metrics_summary.csv`.

**Read this honestly.** At small `eps` the model is close to chance. With only
6 clients there is very little subsampling amplification and the per-client
noise required for `eps = 1` overwhelms a 68k-parameter model. Client-level DP
at single-digit `eps` is a large-population technique — production deployments
use thousands of clients per round. The correct claim is *"the trade-off is
real and measured on this scale"*, not *"DP is free"*.

A tuning note worth keeping: an earlier run used `clip_norm = 1.0` while actual
update norms were ~25. Clipping discarded ~96% of the signal and every DP run
sat at chance. Clipping thresholds must be calibrated to observed update norms.

### Dropout recovery (measured)

```
{'round_id': 1, 'participants': [0, 1, 2, 3], 'survivors': [0, 1, 2],
 'dropped': [3], 'dropout_recovered': True, 'test_accuracy': 0.6483,
 'round_wall_time_s': 66.25, 'server_saw_plaintext_updates': False}
```

### On-device inference (measured)

| Metric | Value |
|---|---|
| Parameters | 68,103 |
| ONNX fp32 | 269.2 KB |
| ONNX INT8 | 264.5 KB |
| Test accuracy through ONNX Runtime | **0.9579** |
| Latency p50 / p95 / p99 | **0.036 / 0.073 / 0.109 ms** |
| External network calls per inference | 0 |

INT8 compression is only 1.02x because most parameters live in an
`EmbeddingBag` that dynamic quantization leaves in fp32; only the two `Gemm`
weights are quantized. Do not claim a 4x win — the honest figure is 1.02x, and
the deployable fact is that the whole model is a quarter of a megabyte.

---

## 6. Threat model and limits

**Protected against:** an *honest-but-curious* server. It sees only masked
`uint32` vectors and aggregate metrics.

**Not protected against:**

* **A malicious server.** It could fabricate sybil clients to isolate a victim's
  update. Bonawitz assumes the server follows the protocol.
* **Malicious clients.** No robustness to poisoning; no input validation on updates.
* **Unreviewed cryptography.** This is a from-scratch research-grade
  implementation. It has had no third-party security audit.
* **Quantization/DP caveat.** Continuous Gaussian noise is added, then
  quantized. Production systems use *discrete* Gaussian or Skellam so the DP
  guarantee survives quantization exactly. The approximation here is standard
  practice but is an approximation.

## 7. Why not Flower or TFF

Secure aggregation is the central privacy claim, so it should be auditable
line by line. Flower's SecAgg+ is a recent, partially-simulated addition, and
TFF's `secure_sum` runs inside a simulation harness rather than over real
client processes. Implementing Bonawitz directly means the server provably has
no code path to an individual update, and that auditability is the
contribution. The counterpoint is stated above: hand-rolled crypto is not
production-hardened.
