"""Download the real SNIPS corpus and partition it NON-IID (Dirichlet) across clients.

Run once:  python -m fl.data.prepare --clients 5 --alpha 0.5

Each client's shard is written to fl_data/client_<id>/train.jsonl and is the ONLY
data that client process ever reads. The server never touches these files.
"""
import argparse
import json
import os
import random
import subprocess
import urllib.request

BASE = ("https://raw.githubusercontent.com/sonos/nlu-benchmark/master/"
        "2017-06-custom-intent-engines")

INTENTS = ["AddToPlaylist", "BookRestaurant", "GetWeather", "PlayMusic",
           "RateBook", "SearchCreativeWork", "SearchScreeningEvent"]

OUT_ROOT = "fl_data"


REPO = "https://github.com/sonos/nlu-benchmark.git"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "ppda", "nlu-benchmark")
SUBDIR = "2017-06-custom-intent-engines"


def _parse(raw: dict, intent: str):
    return ["".join(frag["text"] for frag in item["data"]).strip()
            for item in raw[intent]]


def _fetch_http(intent: str):
    url = f"{BASE}/{intent}/train_{intent}_full.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return _parse(json.loads(r.read().decode("utf-8", errors="ignore")), intent)


def _ensure_clone() -> str:
    """Fallback for environments where raw.githubusercontent is unreachable."""
    if not os.path.isdir(os.path.join(CACHE, ".git")):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        print(f"  cloning {REPO} -> {CACHE}", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO, CACHE],
                       check=True, capture_output=True)
    return os.path.join(CACHE, SUBDIR)


def _fetch_local(root: str, intent: str):
    path = os.path.join(root, intent, f"train_{intent}_full.json")
    with open(path, encoding="utf-8", errors="ignore") as f:
        return _parse(json.load(f), intent)


def download():
    root = None
    try:
        _fetch_http(INTENTS[0])
    except Exception as e:
        print(f"  direct HTTP fetch unavailable ({type(e).__name__}); using git clone")
        root = _ensure_clone()

    corpus = []
    for label, intent in enumerate(INTENTS):
        print(f"  loading {intent} ...", flush=True)
        texts = _fetch_local(root, intent) if root else _fetch_http(intent)
        for text in texts:
            if text:
                corpus.append((text, label))
    return corpus


def dirichlet_partition(corpus, num_clients: int, alpha: float, seed: int = 42):
    """Realistic non-IID split: each client gets a skewed label distribution."""
    import numpy as np
    rng = np.random.default_rng(seed)
    by_label = {}
    for text, lbl in corpus:
        by_label.setdefault(lbl, []).append((text, lbl))

    shards = [[] for _ in range(num_clients)]
    for lbl, items in by_label.items():
        rng.shuffle(items)
        props = rng.dirichlet([alpha] * num_clients)
        cuts = (np.cumsum(props) * len(items)).astype(int)[:-1]
        start = 0
        for cid, cut in enumerate(list(cuts) + [len(items)]):
            shards[cid].extend(items[start:cut])
            start = cut
    for s in shards:
        rng.shuffle(s)
    return shards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=0.5, help="lower = more non-IID")
    ap.add_argument("--test-frac", type=float, default=0.15)
    args = ap.parse_args()

    print("Downloading real SNIPS corpus...")
    corpus = download()
    random.Random(42).shuffle(corpus)
    print(f"Total utterances: {len(corpus)}  |  classes: {len(INTENTS)}")

    n_test = int(len(corpus) * args.test_frac)
    test, train = corpus[:n_test], corpus[n_test:]

    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(os.path.join(OUT_ROOT, "test.jsonl"), "w") as f:
        for t, l in test:
            f.write(json.dumps({"text": t, "label": l}) + "\n")

    shards = dirichlet_partition(train, args.clients, args.alpha)
    for cid, shard in enumerate(shards):
        d = os.path.join(OUT_ROOT, f"client_{cid}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "train.jsonl"), "w") as f:
            for t, l in shard:
                f.write(json.dumps({"text": t, "label": l}) + "\n")
        dist = {}
        for _, l in shard:
            dist[INTENTS[l]] = dist.get(INTENTS[l], 0) + 1
        print(f"client_{cid}: {len(shard)} samples | {dist}")

    with open(os.path.join(OUT_ROOT, "meta.json"), "w") as f:
        json.dump({"intents": INTENTS, "num_classes": len(INTENTS),
                   "num_clients": args.clients, "alpha": args.alpha}, f, indent=2)
    print(f"\nDone. Shards in ./{OUT_ROOT}/")


if __name__ == "__main__":
    main()
