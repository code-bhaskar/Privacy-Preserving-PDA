"""Single-pipeline FL supervisor.

Historically the federated learning demo needed **three** separate things running:

    1. ``uvicorn fl.server.app:app``            (standalone coordinator)
    2. ``python -m fl.client.run --client-id N`` (one shell per client)
    3. ``python -m fl.experiments.run_sweep``    (the epsilon sweep driver)

This module collapses all three into the **one** FastAPI process that already serves
``/api/v1/*`` (see ``app/main.py``, which mounts ``fl.server.routes``). The Angular
frontend can therefore prepare data, spawn clients, run rounds and run the
epsilon sweep from a single pipeline, with no second server and no extra shells.

What is deliberately *not* collapsed: each FL client is still an **independent OS
process** that talks to the coordinator over HTTP and whose training data never
leaves that process. That isolation is the security claim being demonstrated
(honest-but-curious server sees only masked ``uint32`` vectors), so the supervisor
spawns real subprocesses instead of faking clients in-process.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from fl.server.coordinator import Phase, coordinator

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_ROOT = os.path.join(REPO_ROOT, "fl_data")
LOG_ROOT = os.path.join(REPO_ROOT, "logs")
RESULTS_JSON = os.path.join(REPO_ROOT, "fl_results.json")

# The coordinator listens inside this same process, so clients always talk to it
# over loopback. ``127.0.0.1`` (not ``0.0.0.0``) is what a client must dial.
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


def _server_url() -> str:
    """Loopback URL of this app's own coordinator (settings.FL_SERVER_URL)."""
    try:  # imported lazily: ``fl`` must stay usable without the ``app`` package
        from app.core.config import settings
        return settings.FL_SERVER_URL or DEFAULT_SERVER_URL
    except Exception:
        return DEFAULT_SERVER_URL

MAX_SUPERVISED_CLIENTS = 8
_PHASE_ORDER = [p.value for p in Phase]


# --------------------------------------------------------------------------- #
# dataset
# --------------------------------------------------------------------------- #

def dataset_status() -> dict:
    """Is the SNIPS corpus partitioned and ready for clients to read?"""
    meta_path = os.path.join(DATA_ROOT, "meta.json")
    meta: dict = {}
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path))
        except (OSError, ValueError):
            meta = {}

    shards: list[dict] = []
    if os.path.isdir(DATA_ROOT):
        for name in sorted(os.listdir(DATA_ROOT)):
            if not name.startswith("client_"):
                continue
            train = os.path.join(DATA_ROOT, name, "train.jsonl")
            if not os.path.exists(train):
                continue
            with open(train, encoding="utf-8") as fh:
                n = sum(1 for _ in fh)
            shards.append({"client_id": int(name.split("_")[1]), "samples": n})

    test_path = os.path.join(DATA_ROOT, "test.jsonl")
    n_test = 0
    if os.path.exists(test_path):
        with open(test_path, encoding="utf-8") as fh:
            n_test = sum(1 for _ in fh)

    return {
        "ready": bool(meta) and bool(shards) and n_test > 0,
        "data_root": DATA_ROOT,
        "num_classes": meta.get("num_classes"),
        "intents": meta.get("intents", []),
        "alpha": meta.get("alpha"),
        "planned_clients": meta.get("num_clients"),
        "test_samples": n_test,
        "shards": shards,
        "total_train_samples": sum(s["samples"] for s in shards),
    }


class _DatasetJob:
    """Background ``fl.data.prepare`` runner (it clones/downloads SNIPS)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: dict = {"running": False, "exit_code": None,
                            "started_at": None, "finished_at": None, "log": ""}

    def start(self, clients: int, alpha: float) -> dict:
        with self._lock:
            if self.state["running"]:
                return {"started": False, "reason": "dataset preparation already running"}
            self.state = {"running": True, "exit_code": None,
                          "started_at": time.time(), "finished_at": None, "log": ""}
        threading.Thread(target=self._run, args=(clients, alpha),
                         name="fl-data-prepare", daemon=True).start()
        return {"started": True, "clients": clients, "alpha": alpha}

    def _run(self, clients: int, alpha: float) -> None:
        cmd = [sys.executable, "-m", "fl.data.prepare",
               "--clients", str(clients), "--alpha", str(alpha)]
        try:
            proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                                  text=True, timeout=1800)
            out = (proc.stdout or "") + (proc.stderr or "")
            code: Optional[int] = proc.returncode
        except Exception as exc:  # pragma: no cover - defensive
            out = f"{type(exc).__name__}: {exc}"
            code = -1
        with self._lock:
            self.state.update(running=False, exit_code=code,
                              finished_at=time.time(), log=out[-20000:])

    def status(self) -> dict:
        with self._lock:
            snap = dict(self.state)
        snap["dataset"] = dataset_status()
        return snap


dataset_job = _DatasetJob()


# --------------------------------------------------------------------------- #
# client processes
# --------------------------------------------------------------------------- #

@dataclass
class _Client:
    client_id: int
    proc: subprocess.Popen
    log_path: str
    started_at: float
    drop_at: Optional[str] = None
    server_url: str = DEFAULT_SERVER_URL
    rounds: int = 1000

    def alive(self) -> bool:
        return self.proc.poll() is None

    def describe(self) -> dict:
        return {
            "client_id": self.client_id,
            "pid": self.proc.pid,
            "alive": self.alive(),
            "exit_code": self.proc.returncode,
            "started_at": self.started_at,
            "uptime_s": round(time.time() - self.started_at, 1),
            "drop_at": self.drop_at,
            "server_url": self.server_url,
            "log_path": os.path.relpath(self.log_path, REPO_ROOT),
            "shard": os.path.relpath(
                os.path.join(DATA_ROOT, f"client_{self.client_id}"), REPO_ROOT),
        }


class ClientSupervisor:
    """Spawn / inspect / stop the independent FL client OS processes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: dict[int, _Client] = {}
        os.makedirs(LOG_ROOT, exist_ok=True)

    # ---------------- queries ---------------- #

    def list(self) -> list[dict]:
        with self._lock:
            return [c.describe() for c in sorted(self._clients.values(),
                                                 key=lambda c: c.client_id)]

    def log_tail(self, client_id: int, lines: int = 40) -> dict:
        with self._lock:
            client = self._clients.get(client_id)
        if client is None:
            return {"client_id": client_id, "found": False, "lines": []}
        try:
            with open(client.log_path, encoding="utf-8", errors="ignore") as fh:
                tail = fh.read().splitlines()[-max(1, min(lines, 500)):]
        except OSError as exc:
            tail = [f"<cannot read log: {exc}>"]
        return {"client_id": client_id, "found": True,
                "alive": client.alive(), "lines": tail}

    def registered_with_coordinator(self) -> dict:
        with coordinator.lock:
            return {
                "registered_clients": len(coordinator.registered),
                "clients": [
                    {"client_id": cid, "num_samples": info.get("num_samples"),
                     "last_seen_age_s": round(time.time() - info.get("last_seen", 0), 1)}
                    for cid, info in sorted(coordinator.registered.items())
                ],
            }

    # ---------------- lifecycle ---------------- #

    def spawn(self, count: int = 3, start_id: int = 0,
              server_url: Optional[str] = None,
              drop_at: Optional[str] = None,
              rounds: int = 1000) -> dict:
        server_url = (server_url or _server_url()).rstrip("/")
        count = max(1, min(int(count), MAX_SUPERVISED_CLIENTS))
        if not dataset_status()["ready"]:
            return {"spawned": [], "error":
                    "fl_data is not prepared. Call POST /api/v1/federated/pipeline/dataset/prepare first."}

        spawned: list[dict] = []
        errors: list[str] = []
        with self._lock:
            for cid in range(start_id, start_id + count):
                if len(self._clients) >= MAX_SUPERVISED_CLIENTS:
                    errors.append(f"supervisor cap reached ({MAX_SUPERVISED_CLIENTS})")
                    break
                existing = self._clients.get(cid)
                if existing is not None and existing.alive():
                    spawned.append(existing.describe())
                    continue
                log_path = os.path.join(LOG_ROOT, f"client_{cid}.log")
                cmd = [sys.executable, "-m", "fl.client.run",
                       "--client-id", str(cid),
                       "--server-url", server_url,
                       "--rounds", str(rounds)]
                if drop_at:
                    cmd += ["--drop-at", drop_at]
                try:
                    log_fh = open(log_path, "a", encoding="utf-8")
                    log_fh.write(f"\n=== spawned {time.strftime('%Y-%m-%d %H:%M:%S')} "
                                 f"({' '.join(cmd)}) ===\n")
                    log_fh.flush()
                    proc = subprocess.Popen(
                        cmd, cwd=REPO_ROOT, stdout=log_fh, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, start_new_session=True)
                except Exception as exc:
                    errors.append(f"client {cid}: {type(exc).__name__}: {exc}")
                    continue
                client = _Client(client_id=cid, proc=proc, log_path=log_path,
                                 started_at=time.time(), drop_at=drop_at,
                                 server_url=server_url, rounds=rounds)
                self._clients[cid] = client
                spawned.append(client.describe())
        return {"spawned": spawned, "errors": errors}

    def stop(self, client_ids: Optional[list[int]] = None) -> dict:
        with self._lock:
            targets = (list(self._clients.values()) if not client_ids
                       else [self._clients[c] for c in client_ids if c in self._clients])
            stopped = []
            for client in targets:
                if client.alive():
                    try:
                        os.killpg(os.getpgid(client.proc.pid), 15)
                    except (ProcessLookupError, PermissionError):
                        client.proc.terminate()
                try:
                    client.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(client.proc.pid), 9)
                    except (ProcessLookupError, PermissionError):
                        client.proc.kill()
                stopped.append(client.client_id)
                self._clients.pop(client.client_id, None)
        return {"stopped": stopped}

    def stop_all(self) -> dict:
        return self.stop(None)


supervisor = ClientSupervisor()


# --------------------------------------------------------------------------- #
# epsilon sweep (single-pipeline replacement for fl.experiments.run_sweep)
# --------------------------------------------------------------------------- #

@dataclass
class _SweepState:
    running: bool = False
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    epsilons: list = field(default_factory=list)
    rounds: int = 0
    clients_per_round: int = 0
    current_epsilon: Optional[float] = None
    current_epsilon_label: str = ""
    completed_rounds: int = 0
    total_rounds: int = 0
    points: list = field(default_factory=list)
    rounds_log: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": round((self.finished_at or time.time()) - self.started_at, 1)
            if self.started_at else None,
            "epsilons": self.epsilons,
            "rounds": self.rounds,
            "clients_per_round": self.clients_per_round,
            "current_epsilon": self.current_epsilon,
            "current_epsilon_label": self.current_epsilon_label,
            "completed_rounds": self.completed_rounds,
            "total_rounds": self.total_rounds,
            "progress_pct": round(100.0 * self.completed_rounds / self.total_rounds, 1)
            if self.total_rounds else 0.0,
            "points": self.points,
            "rounds_log": self.rounds_log[-60:],
            "error": self.error,
        }


def _eps_label(eps: Optional[float]) -> str:
    return "no DP (ε=∞)" if eps is None else f"ε={eps:g}"


class SweepRunner:
    """Runs the (ε, accuracy) sweep inside the API process, in a worker thread.

    Same protocol as ``fl.experiments.run_sweep`` — real client processes, real
    Bonawitz secure aggregation, real Rényi DP accounting — but with **live
    progress** the frontend can poll, and no separate driver process.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = _SweepState()

    def status(self) -> dict:
        with self._lock:
            return self._state.to_dict()

    def start(self, epsilons: list, rounds: int, clients_per_round: int,
              local_epochs: int, clip_norm: float, lr: float,
              delta: float) -> dict:
        with self._lock:
            if self._state.running:
                return {"started": False, "reason": "a sweep is already running"}
            registered = len(coordinator.registered)
            if registered < clients_per_round:
                return {"started": False,
                        "reason": f"need {clients_per_round} connected clients, "
                                  f"have {registered}. Spawn clients first."}
            self._state = _SweepState(
                running=True, started_at=time.time(), epsilons=list(epsilons),
                rounds=rounds, clients_per_round=clients_per_round,
                total_rounds=rounds * len(epsilons))
        threading.Thread(target=self._run,
                         args=(list(epsilons), rounds, clients_per_round,
                               local_epochs, clip_norm, lr, delta),
                         name="fl-sweep", daemon=True).start()
        return {"started": True, "epsilons": epsilons, "rounds": rounds,
                "clients_per_round": clients_per_round}

    def _wait_round(self, timeout_s: float) -> dict:
        """Block until the coordinator finishes the round it is on."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            phase = coordinator.phase
            if phase == Phase.DONE and coordinator.history:
                return coordinator.history[-1]
            if phase == Phase.IDLE:
                raise RuntimeError("coordinator went IDLE mid-round")
            time.sleep(0.2)
        raise TimeoutError(f"round did not finish within {timeout_s:.0f}s "
                           f"(phase={coordinator.phase.value}, "
                           f"collected={len(coordinator.masked)}/"
                           f"{len(coordinator.participants)})")

    def _run(self, epsilons: list, rounds: int, clients_per_round: int,
             local_epochs: int, clip_norm: float, lr: float, delta: float) -> None:
        points: list[dict] = []
        try:
            for eps in epsilons:
                coordinator.reset_experiment(drop_registrations=False)
                with self._lock:
                    self._state.current_epsilon = eps
                    self._state.current_epsilon_label = _eps_label(eps)
                    self._state.points = []

                accs, walls, losses = [], [], []
                for r in range(rounds):
                    coordinator.start_round(
                        clients_per_round=clients_per_round,
                        local_epochs=local_epochs,
                        lr=lr,
                        clip_norm=clip_norm,
                        target_epsilon=eps,
                        total_rounds_planned=rounds,
                        delta=delta,
                    )
                    rec = self._wait_round(timeout_s=300.0)
                    accs.append(rec["test_accuracy"])
                    walls.append(rec["round_wall_time_s"])
                    losses.append(rec["test_loss"])
                    row = {
                        "epsilon": eps,
                        "epsilon_label": _eps_label(eps),
                        "round": rec["round_id"],
                        "test_accuracy": rec["test_accuracy"],
                        "test_loss": rec["test_loss"],
                        "noise_multiplier": rec["noise_multiplier"],
                        "wall_time_s": rec["round_wall_time_s"],
                        "survivors": rec["survivors"],
                        "dropped": rec["dropped"],
                        "total_uplink_bytes": rec["total_uplink_bytes"],
                        "privacy_spent": rec["privacy_spent"],
                        "server_saw_plaintext_updates":
                            rec["server_saw_plaintext_updates"],
                    }
                    with self._lock:
                        self._state.rounds_log.append(row)
                        self._state.completed_rounds += 1
                        self._state.points = list(points)

                point = {
                    "epsilon": eps,
                    "epsilon_label": _eps_label(eps),
                    "final_accuracy": round(accs[-1], 4) if accs else 0.0,
                    "mean_accuracy": round(sum(accs) / len(accs), 4) if accs else 0.0,
                    "accuracy_curve": [round(a, 4) for a in accs],
                    "final_loss": round(losses[-1], 4) if losses else None,
                    "avg_round_wall_time_s": round(sum(walls) / len(walls), 2)
                    if walls else None,
                    "noise_multiplier": round(
                        coordinator.history[-1]["noise_multiplier"], 4)
                    if coordinator.history else None,
                    "privacy_spent": coordinator.history[-1]["privacy_spent"]
                    if coordinator.history else None,
                    "comm_bytes_per_client": coordinator.dim * 4,
                    "model_size_bytes": coordinator.dim * 4,
                    "rounds": rounds,
                }
                points.append(point)
                with self._lock:
                    self._state.points = list(points)

            payload = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "config": {"epsilons": epsilons, "rounds": rounds,
                           "clients_per_round": clients_per_round,
                           "local_epochs": local_epochs, "clip_norm": clip_norm,
                           "lr": lr, "delta": delta},
                "points": points,
                "rounds_log": self._state.rounds_log,
                "note": "Run through the single-pipeline supervisor "
                        "(fl/pipeline/supervisor.py) from the Angular UI.",
            }
            with open(RESULTS_JSON, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            with self._lock:
                self._state.error = None
        except Exception as exc:
            with self._lock:
                self._state.error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._state.running = False
                self._state.finished_at = time.time()
                self._state.current_epsilon_label = ""
                self._state.points = list(points)


sweep_runner = SweepRunner()


# --------------------------------------------------------------------------- #
# one-call demo pipeline
# --------------------------------------------------------------------------- #

def pipeline_status(server_url: Optional[str] = None) -> dict:
    """Everything the Angular 'Federated pipeline' tab renders, in one call."""
    server_url = (server_url or _server_url()).rstrip("/")
    clients = supervisor.list()
    status = coordinator.status()
    ds = dataset_status()
    return {
        "single_pipeline": True,
        "coordinator_in_process": True,
        "coordinator_url": f"{server_url}/api/v1/fl",
        "server_url": server_url,
        "phases": _PHASE_ORDER,
        "dataset": ds,
        "dataset_job": dataset_job.status(),
        "clients": clients,
        "clients_alive": sum(1 for c in clients if c["alive"]),
        "registered": supervisor.registered_with_coordinator(),
        # Clients that registered with the coordinator but were started OUTSIDE
        # the supervisor (e.g. `python -m fl.client.run` in a terminal, or
        # scripts/run_fl_demo.sh). They do take part in rounds, but the UI's
        # stop/log controls cannot manage them, so they are reported separately
        # rather than letting the panel read "0 alive" next to "3 registered".
        "registered_not_supervised": _registered_not_supervised(clients),
        "round": status,
        "model_dim": coordinator.dim,
        "model_size_bytes": coordinator.dim * 4,
        "sweep": sweep_runner.status(),
        "privacy_spent": coordinator.accountant.spent() if coordinator.accountant else None,
        "history": coordinator.history[-25:],
        "history_count": len(coordinator.history),
        "results_file": os.path.relpath(RESULTS_JSON, REPO_ROOT),
        "results_file_exists": os.path.exists(RESULTS_JSON),
        "python_executable": sys.executable,
        # Two distinct artifacts. The federated one is trained on SNIPS (7
        # intents); the live one is what /assistant/command serves (8 assistant
        # intents). Exporting never overwrites the live model -- the label
        # spaces differ, so swapping them would mislabel every intent.
        "onnx_artifact": _rel("deployed_models", "intent_model_federated.onnx"),
        "onnx_artifact_exists": _exists("deployed_models", "intent_model_federated.onnx"),
        "live_model_artifact": _rel("deployed_models", "intent_model.onnx"),
        "live_model_artifact_exists": _exists("deployed_models", "intent_model.onnx"),
        "live_model_classes": len(_assistant_labels()),
        "federated_model_classes": coordinator.num_classes,
        "artifacts": {
            "accuracy_plot": "results/accuracy_vs_epsilon.png",
            "metrics_csv": "results/metrics_summary.csv",
            "federated_onnx": _rel("deployed_models", "intent_model_federated.onnx"),
            "federated_int8": _rel("deployed_models", "intent_int8_federated.onnx"),
            "live_onnx": _rel("deployed_models", "intent_model.onnx"),
            "benchmark": _rel("deployed_models", "benchmark.json"),
            "model_card": _rel("deployed_models", "model_card_federated.json"),
            "export_log": _rel("logs", "onnx_export.log"),
        },
    }


def _registered_not_supervised(clients: list) -> list:
    """Coordinator-registered client ids the supervisor does not own."""
    supervised = {c.get("client_id") for c in clients}
    with coordinator.lock:
        return sorted(cid for cid in coordinator.registered if cid not in supervised)


def _rel(*parts: str) -> str:
    return os.path.relpath(os.path.join(REPO_ROOT, *parts), REPO_ROOT)


def _exists(*parts: str) -> bool:
    return os.path.exists(os.path.join(REPO_ROOT, *parts))


def _assistant_labels() -> list:
    try:
        from app.Data_sets.intent.intent_seed import INTENT_LABELS
        return list(INTENT_LABELS)
    except Exception:  # pragma: no cover - fl usable without the app package
        return []


def shutdown() -> None:
    """Stop supervised clients (called from the FastAPI lifespan shutdown)."""
    try:
        supervisor.stop_all()
    except Exception:  # pragma: no cover - best effort on shutdown
        pass


def onnx_export_available() -> bool:
    return shutil.which(sys.executable) is not None or os.path.exists(sys.executable)
