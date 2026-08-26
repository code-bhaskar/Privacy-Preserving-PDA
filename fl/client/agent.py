"""A real federated client. Its training data NEVER leaves this process."""
import json
import os
import time
from typing import Optional

import numpy as np
import requests
import torch
import torch.nn as nn

torch.set_num_threads(1)   # keep N concurrent client processes from thrashing
from torch.utils.data import DataLoader

from fl.data.dataset import IntentDataset, collate
from fl.model.net import IntentNet, flatten_state, unflatten_state
from fl.privacy.dp_client import add_distributed_noise, clip_update
from fl.protocol.quantize import quantize
from fl.protocol.secagg import ClientSecAgg


class StaleRound(Exception):
    """The coordinator advanced past the round we were working on."""


class FederatedClient:
    def __init__(self, client_id: int, server_url: str, data_dir: str,
                 num_classes: int = 7, drop_at_phase: Optional[str] = None):
        self.id = client_id
        self.url = server_url.rstrip("/")
        self.drop_at_phase = drop_at_phase  # to demo dropout recovery
        self.rng = np.random.default_rng(1000 + client_id)

        path = os.path.join(data_dir, "train.jsonl")
        rows = []
        for line in open(path):
            o = json.loads(line)
            rows.append((o["text"], o["label"]))
        self.dataset = IntentDataset(rows)
        self.n = len(rows)

        self.model = IntentNet(num_classes)
        self.template = self.model.state_dict()
        print(f"[client {self.id}] loaded {self.n} PRIVATE samples from {path}",
              flush=True)

    # ---------- http ----------
    def _post(self, ep, payload):
        r = requests.post(f"{self.url}{ep}", json=payload, timeout=180)
        r.raise_for_status()
        return r.json()

    def _get(self, ep):
        r = requests.get(f"{self.url}{ep}", timeout=180)
        r.raise_for_status()
        return r.json()

    def register(self):
        return self._post("/api/v1/fl/register",
                          {"client_id": self.id, "num_samples": self.n})

    def _wait(self, want, timeout=600, round_id=None):
        t0 = time.time()
        while time.time() - t0 < timeout:
            s = self._get("/api/v1/fl/round/status")
            if round_id is not None and s["round_id"] != round_id:
                raise StaleRound(f"server moved to round {s['round_id']}")
            if s["phase"] == want:
                return s
            time.sleep(2.0)
        raise TimeoutError(f"timeout waiting for phase {want}")

    # ---------- local training (the actual ML) ----------
    def local_train(self, global_flat: np.ndarray, epochs: int, lr: float):
        self.model.load_state_dict(unflatten_state(global_flat, self.template))
        self.model.train()
        opt = torch.optim.SGD(self.model.parameters(), lr=lr, momentum=0.9)
        crit = nn.CrossEntropyLoss()
        dl = DataLoader(self.dataset, batch_size=32, shuffle=True, collate_fn=collate)

        last = 0.0
        for ep in range(epochs):
            tot, nb = 0.0, 0
            for idx, off, y in dl:
                opt.zero_grad()
                loss = crit(self.model(idx, off), y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 5.0)
                opt.step()
                tot += loss.item()
                nb += 1
            last = tot / max(nb, 1)
            print(f"[client {self.id}]   epoch {ep+1}/{epochs} loss={last:.4f}",
                  flush=True)
        return flatten_state(self.model.state_dict()), last

    # ---------- one full round ----------
    def run_round(self):
        cfg = self._wait("ADVERTISE_KEYS")["config"]
        if cfg["round_id"] == getattr(self, "_last_round", None):
            time.sleep(0.5)   # already handled this round; wait for the next
            return None
        self._last_round = cfg["round_id"]
        if self.id not in cfg["participants"]:
            # Back off hard: idle pollers otherwise steal CPU from the
            # clients that are actually training this round.
            print(f"[client {self.id}] not selected for round {cfg['round_id']}",
                  flush=True)
            time.sleep(8)
            return None

        rid = cfg["round_id"]
        sa = ClientSecAgg(self.id, cfg["threshold"], rid)
        print(f"[client {self.id}] === round {rid} ===", flush=True)

        # Phase 1: advertise keys
        self._post("/api/v1/fl/keys/advertise",
                   {"client_id": self.id, **sa.public_keys()})
        st = self._wait("SHARE_KEYS", round_id=rid)
        peers = {int(k): {"c_pk": bytes.fromhex(v["c_pk"]),
                          "s_pk": bytes.fromhex(v["s_pk"])}
                 for k, v in st["peer_pubkeys"].items()}

        # Phase 2: distribute Shamir shares (sealed - server cannot read them)
        self._post("/api/v1/fl/keys/share",
                   {"client_id": self.id,
                    "shares": {str(k): v for k, v in sa.make_shares(peers).items()}})
        self._wait("COLLECT", round_id=rid)
        sa.store_shares({int(k): v for k, v in
                         self._get(f"/api/v1/fl/keys/inbox/{self.id}")["shares"].items()})

        if self.drop_at_phase == "COLLECT":
            print(f"[client {self.id}] *** SIMULATING DROPOUT ***", flush=True)
            st = self._wait("UNMASK", timeout=900, round_id=rid)
            rev = sa.reveal(st["survivors"], st["dropped"])
            # a dropped client contributes nothing; it just stops here
            return {"dropped": True}

        # Phase 3: real local training on private data
        gw = self._get("/api/v1/fl/model/weights")
        global_flat = np.frombuffer(bytes.fromhex(gw["weights_hex"]),
                                    dtype=np.float32).copy()
        local_flat, loss = self.local_train(global_flat, cfg["local_epochs"], cfg["lr"])

        # Phase 4: client-level DP
        delta = local_flat - global_flat
        clipped, raw_norm = clip_update(delta, cfg["clip_norm"])
        noised = add_distributed_noise(
            clipped, cfg["clip_norm"], cfg["noise_multiplier"],
            cfg["num_clients_in_round"], self.rng)
        print(f"[client {self.id}] ||delta||={raw_norm:.3f} "
              f"clip={cfg['clip_norm']} sigma_mult={cfg['noise_multiplier']:.3f}",
              flush=True)

        # Phase 5: quantize + mask. Only this leaves the process.
        q = quantize(noised, cfg["clip_norm"] * 2.0)
        y = sa.mask_vector(q, cfg["participants"])
        self._post("/api/v1/fl/update/masked",
                   {"client_id": self.id, "vector_hex": y.tobytes().hex(),
                    "num_samples": self.n})

        # Phase 6: unmasking assistance
        st = self._wait("UNMASK", timeout=900, round_id=rid)
        rev = sa.reveal(st["survivors"], st["dropped"])
        self._post("/api/v1/fl/update/reveal", {"client_id": self.id, **rev})
        print(f"[client {self.id}] round {rid} complete (local loss {loss:.4f})",
              flush=True)
        return {"round_id": rid, "local_loss": loss}
