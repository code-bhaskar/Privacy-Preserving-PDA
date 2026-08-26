import time
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import train_test_split

from app.Data_sets.intent.intent_seed import INTENT_DATA, INTENT_LABELS
from app.core.config import settings
from app.ml_models.intent_classifier import IntentClassifier
from app.utils.dp_utils import clip_l2, add_gaussian_noise, pairwise_masks


class FederatedSimulator:
    """
    Simulates N clients holding disjoint local partitions.

    Trust boundary enforced in code:
      * `_client_local_update()` is the ONLY place raw text is touched.
      * It returns a masked, DP-noised float vector — nothing else.
      * `run_round()` (the coordinator) never receives text, labels or counts
        beyond a sample count used for logging.
    """

    def __init__(self):
        self.base = IntentClassifier()
        self.base.fit_global()
        self.dim = self.base.vector_dim()
        self._partition()

    # ---------- data partitioning (client-side, never leaves client) ----------
    def _partition(self, n_clients: int | None = None, seed: int = 42):
        n_clients = n_clients or settings.FL_CLIENT_COUNT
        X_text = [t for t, _ in INTENT_DATA]
        y = [l for _, l in INTENT_DATA]
        Xtr, Xte, ytr, yte = train_test_split(
            X_text, y, test_size=0.25, random_state=seed, stratify=y
        )
        self.X_test, self.y_test = self.base.transform(Xte), np.array(yte)

        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(Xtr))
        shards = np.array_split(idx, n_clients)
        self.clients = []
        for k, shard in enumerate(shards):
            texts = [Xtr[i] for i in shard]
            labels = [ytr[i] for i in shard]
            self.clients.append({
                "client_id": f"client-{k + 1}",
                "X": self.base.transform(texts),
                "y": np.array(labels),
                "n": len(texts),
            })

    # ---------- client side ----------
    def _client_local_update(self, client: dict, global_w: np.ndarray,
                             epsilon: float | None, rng: np.random.Generator
                             ) -> tuple[np.ndarray, int]:
        local = SGDClassifier(loss="log_loss", alpha=1e-4, random_state=0)
        local.partial_fit(client["X"], client["y"], classes=np.array(INTENT_LABELS))
        n_coef = local.coef_.size
        local.coef_ = global_w[:n_coef].reshape(local.coef_.shape)
        local.intercept_ = global_w[n_coef:].reshape(local.intercept_.shape)

        for _ in range(settings.FL_LOCAL_EPOCHS):
            local.partial_fit(client["X"], client["y"], classes=np.array(INTENT_LABELS))

        local_w = np.concatenate([local.coef_.ravel(), local.intercept_.ravel()])
        delta = local_w - global_w                                   # model update only
        delta = clip_l2(delta, settings.FL_CLIP_NORM)                # bound sensitivity
        delta = add_gaussian_noise(delta, settings.FL_CLIP_NORM,     # FR-12
                                   epsilon, settings.FL_DP_DELTA, rng)
        return delta, client["n"]

    # ---------- coordinator side ----------
    def run_round(self, round_id: int, global_w: np.ndarray,
                  epsilon: float | None, secure_agg: bool = True) -> dict:
        t0 = time.perf_counter()
        rng = np.random.default_rng(round_id)
        ids = [c["client_id"] for c in self.clients]
        masks = pairwise_masks(ids, self.dim, round_id) if secure_agg \
            else {cid: np.zeros(self.dim) for cid in ids}

        received, contributions = [], []
        for c in self.clients:
            delta, n = self._client_local_update(c, global_w, epsilon, rng)
            transmitted = delta + masks[c["client_id"]]     # FR-13: masked on the wire
            received.append(transmitted)
            contributions.append({
                "client_id": c["client_id"],
                "n_local_samples": n,
                "payload_bytes": transmitted.nbytes,
                "dp_epsilon": epsilon,
                "masked": secure_agg,
                "raw_data_transmitted": False,
            })

        # masks cancel in the sum → coordinator recovers only the aggregate
        aggregate = np.sum(received, axis=0) / len(received)
        new_w = global_w + aggregate
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "round_id": round_id,
            "weights": new_w,
            "contributions": contributions,
            "latency_ms": latency_ms,
            "comm_bytes_total": sum(c["payload_bytes"] for c in contributions),
            "model_size_bytes": new_w.nbytes,
        }

    # ---------- evaluation ----------
    def evaluate(self, weights: np.ndarray) -> float:
        self.base.set_weights(weights)
        preds = self.base.model.predict(self.X_test)
        return float(np.mean(preds == self.y_test))

    def initial_weights(self) -> np.ndarray:
        fresh = IntentClassifier()
        fresh.fit_global()
        return fresh.get_weights() * 0.0

    def centralized_baseline(self) -> float:
        m = IntentClassifier()
        m.fit_global()
        return float(np.mean(m.model.predict(self.X_test) == self.y_test))


federated_simulator = FederatedSimulator()
