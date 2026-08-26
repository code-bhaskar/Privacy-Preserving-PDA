"""Round state machine. Holds ONLY masked vectors and public keys."""
import json
import os
import threading
import time
from enum import Enum
from typing import Dict, List, Optional

import numpy as np

from fl.model.net import IntentNet, flatten_state, num_params, unflatten_state
from fl.privacy.accountant import PrivacyAccountant, sigma_for_target_epsilon
from fl.protocol.quantize import dequantize_sum
from fl.protocol.secagg import ServerSecAgg

DATA_ROOT = "fl_data"


class Phase(str, Enum):
    IDLE = "IDLE"
    ADVERTISE_KEYS = "ADVERTISE_KEYS"
    SHARE_KEYS = "SHARE_KEYS"
    COLLECT = "COLLECT"
    UNMASK = "UNMASK"
    AGGREGATING = "AGGREGATING"
    DONE = "DONE"


def _num_classes() -> int:
    meta = os.path.join(DATA_ROOT, "meta.json")
    if os.path.exists(meta):
        return json.load(open(meta))["num_classes"]
    return 7


class Coordinator:
    def __init__(self, num_classes: Optional[int] = None):
        self.lock = threading.RLock()
        self.num_classes = num_classes or _num_classes()
        self.model = IntentNet(self.num_classes)
        self.template = self.model.state_dict()
        self.dim = num_params(self.model)

        self.registered: Dict[int, dict] = {}
        self.round_id = 0
        self.phase = Phase.IDLE
        self.config: dict = {}
        self.history: List[dict] = []
        self.accountant: Optional[PrivacyAccountant] = None
        self._test_rows = None
        self._reset_round_state()

    # ---------- lifecycle ----------

    def _reset_round_state(self):
        self.pubkeys: Dict[int, dict] = {}
        self.share_inbox: Dict[int, Dict[int, str]] = {}
        self.masked: Dict[int, np.ndarray] = {}
        self.sample_counts: Dict[int, int] = {}
        self.b_pool: Dict[int, List] = {}
        self.s_pool: Dict[int, List] = {}
        self.participants: List[int] = []
        self.survivors: List[int] = []
        self.dropped: List[int] = []
        self.revealed: List[int] = []

    def register(self, client_id: int, num_samples: int) -> dict:
        with self.lock:
            self.registered[client_id] = {"num_samples": num_samples,
                                          "last_seen": time.time()}
            return {"client_id": client_id, "model_dim": self.dim,
                    "num_classes": self.num_classes,
                    "registered_clients": len(self.registered)}

    def reset_experiment(self, drop_registrations: bool = False):
        """Fresh model + fresh privacy ledger (used between epsilon sweeps)."""
        with self.lock:
            if drop_registrations:
                # Stale ids from a previous topology would otherwise be sampled
                # into a round no live process is listening for.
                self.registered = {}
            self.model = IntentNet(self.num_classes)
            self.template = self.model.state_dict()
            self.history = []
            self.accountant = None
            self.round_id = 0
            self.phase = Phase.IDLE
            self._reset_round_state()
            return {"reset": True}

    def start_round(self, clients_per_round: int, local_epochs: int, lr: float,
                    clip_norm: float, target_epsilon: Optional[float],
                    total_rounds_planned: int, delta: float = 1e-5) -> dict:
        with self.lock:
            if self.phase not in (Phase.IDLE, Phase.DONE):
                raise RuntimeError(f"round in progress (phase={self.phase})")
            if len(self.registered) < clients_per_round:
                raise RuntimeError(
                    f"need {clients_per_round} clients, have {len(self.registered)}")

            self.round_id += 1
            self._reset_round_state()

            ids = sorted(self.registered.keys())
            rng = np.random.default_rng(self.round_id)
            self.participants = sorted(
                rng.choice(ids, size=clients_per_round, replace=False).tolist())

            if self.accountant is None:
                self.accountant = PrivacyAccountant(
                    len(self.registered), clients_per_round, delta)

            if target_epsilon is None:
                sigma = 0.0
            else:
                sigma = sigma_for_target_epsilon(
                    self.accountant.q, total_rounds_planned, target_epsilon, delta)

            self.config = {
                "round_id": self.round_id,
                "participants": self.participants,
                "threshold": max(2, (clients_per_round // 2) + 1),
                "local_epochs": local_epochs,
                "lr": lr,
                "clip_norm": clip_norm,
                "noise_multiplier": sigma,
                "target_epsilon": target_epsilon,
                "num_clients_in_round": clients_per_round,
                "model_dim": self.dim,
            }
            self.phase = Phase.ADVERTISE_KEYS
            self._round_started_at = time.perf_counter()
            return self.config

    # ---------- phase handlers ----------

    def submit_pubkeys(self, cid: int, c_pk: str, s_pk: str):
        with self.lock:
            self._require(Phase.ADVERTISE_KEYS, cid)
            self.pubkeys[cid] = {"c_pk": c_pk, "s_pk": s_pk}
            if len(self.pubkeys) == len(self.participants):
                self.phase = Phase.SHARE_KEYS

    def submit_shares(self, cid: int, shares: Dict[str, str]):
        with self.lock:
            self._require(Phase.SHARE_KEYS, cid)
            for target, blob in shares.items():
                self.share_inbox.setdefault(int(target), {})[cid] = blob
            self.share_inbox.setdefault(cid, {})
            need = len(self.participants) - 1
            complete = [c for c in self.participants
                        if len(self.share_inbox.get(c, {})) >= need]
            if len(complete) == len(self.participants):
                self.phase = Phase.COLLECT

    def submit_masked(self, cid: int, vector_hex: str, num_samples: int):
        with self.lock:
            self._require(Phase.COLLECT, cid)
            self.masked[cid] = np.frombuffer(bytes.fromhex(vector_hex),
                                             dtype="<u4").copy()
            self.sample_counts[cid] = num_samples
            if len(self.masked) == len(self.participants):
                self._close_collection()

    def _close_collection(self):
        self.survivors = sorted(self.masked.keys())
        self.dropped = [c for c in self.participants if c not in self.masked]
        self.phase = Phase.UNMASK

    def force_close_collection(self):
        """Called on timeout - this is how real dropout recovery gets exercised."""
        with self.lock:
            if self.phase == Phase.COLLECT and \
                    len(self.masked) >= self.config["threshold"]:
                self._close_collection()
                return True
            return False

    def submit_reveal(self, cid: int, b_shares: dict, s_shares: dict):
        with self.lock:
            self._require(Phase.UNMASK, cid)
            if cid in self.revealed:
                return
            self.revealed.append(cid)
            for owner, pair in b_shares.items():
                self.b_pool.setdefault(int(owner), []).append(pair)
            for owner, pair in s_shares.items():
                self.s_pool.setdefault(int(owner), []).append(pair)

            t = self.config["threshold"]
            # Wait for EVERY survivor to report. Aggregating at the bare
            # threshold would strand slower clients mid-round.
            have_shares = (len(self.b_pool) == len(self.survivors)
                           and all(len(v) >= t for v in self.b_pool.values()))
            if self.dropped:
                have_shares = have_shares and all(
                    len(self.s_pool.get(d, [])) >= t for d in self.dropped)
            if have_shares and len(self.revealed) == len(self.survivors):
                self._aggregate()

    # ---------- aggregation ----------

    def _aggregate(self):
        self.phase = Phase.AGGREGATING
        cfg = self.config
        clip = cfg["clip_norm"]
        n = len(self.survivors)

        summed_q = ServerSecAgg.aggregate(
            masked=self.masked,
            b_share_pool=self.b_pool,
            s_share_pool=self.s_pool,
            pubkeys={k: {"s_pk": bytes.fromhex(v["s_pk"])}
                     for k, v in self.pubkeys.items()},
            live_ids=self.survivors,
            dropped_ids=self.dropped,
            threshold=cfg["threshold"],
            round_id=self.round_id,
        )

        summed_delta = dequantize_sum(summed_q, clip * 2.0, n)
        avg_delta = (summed_delta / n).astype(np.float32)

        global_flat = flatten_state(self.model.state_dict())
        self.model.load_state_dict(
            unflatten_state(global_flat + avg_delta, self.template))

        if cfg["noise_multiplier"] > 0:
            self.accountant.step(cfg["noise_multiplier"])

        acc, loss = self.evaluate()
        wall = time.perf_counter() - getattr(
            self, "_round_started_at", time.perf_counter())
        record = {
            "round_wall_time_s": round(wall, 2),
            "round_id": self.round_id,
            "participants": self.participants,
            "survivors": self.survivors,
            "dropped": self.dropped,
            "dropout_recovered": len(self.dropped) > 0,
            "test_accuracy": round(acc, 4),
            "test_loss": round(loss, 4),
            "clip_norm": clip,
            "noise_multiplier": round(cfg["noise_multiplier"], 4),
            "target_epsilon": cfg["target_epsilon"],
            "privacy_spent": self.accountant.spent(),
            "bytes_per_client_uplink": self.dim * 4,
            "total_uplink_bytes": self.dim * 4 * n,
            "server_saw_plaintext_updates": False,
        }
        self.history.append(record)
        self.phase = Phase.DONE
        return record

    def evaluate(self) -> tuple[float, float]:
        import torch
        from torch.utils.data import DataLoader

        from fl.data.dataset import IntentDataset, collate

        if self._test_rows is None:
            path = os.path.join(DATA_ROOT, "test.jsonl")
            if not os.path.exists(path):
                return 0.0, 0.0
            rows = []
            for line in open(path):
                o = json.loads(line)
                rows.append((o["text"], o["label"]))
            self._test_rows = rows

        dl = DataLoader(IntentDataset(self._test_rows), batch_size=256,
                        collate_fn=collate)
        self.model.eval()
        crit = torch.nn.CrossEntropyLoss(reduction="sum")
        correct = total = 0
        loss_sum = 0.0
        with torch.no_grad():
            for idx, off, y in dl:
                out = self.model(idx, off)
                loss_sum += crit(out, y).item()
                correct += (out.argmax(1) == y).sum().item()
                total += y.size(0)
        return correct / max(total, 1), loss_sum / max(total, 1)

    # ---------- helpers ----------

    def _require(self, phase: Phase, cid: int):
        if self.phase != phase:
            raise RuntimeError(f"wrong phase: server={self.phase}, expected={phase}")
        if cid not in self.participants:
            raise RuntimeError(f"client {cid} not selected this round")

    def status(self) -> dict:
        with self.lock:
            expose_keys = self.phase in (Phase.SHARE_KEYS, Phase.COLLECT,
                                         Phase.UNMASK, Phase.AGGREGATING, Phase.DONE)
            return {
                "phase": self.phase.value,
                "round_id": self.round_id,
                "config": self.config,
                "peer_pubkeys": self.pubkeys if expose_keys else {},
                "survivors": self.survivors,
                "dropped": self.dropped,
                "registered_clients": len(self.registered),
                "collected": len(self.masked),
            }

    def global_weights_hex(self) -> str:
        with self.lock:
            return flatten_state(self.model.state_dict()).tobytes().hex()

    def inbox_for(self, cid: int) -> Dict[int, str]:
        with self.lock:
            return self.share_inbox.get(cid, {})


coordinator = Coordinator()
