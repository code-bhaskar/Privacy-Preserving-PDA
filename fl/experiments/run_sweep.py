"""Produces the accuracy-vs-epsilon curve required by the PRD (FR-18)."""
import argparse
import json
import time

import requests


def wait_done(url, rid, timeout=1800, grace=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = requests.get(f"{url}/api/v1/fl/round/status").json()
        if s["phase"] == "DONE" and s["round_id"] == rid:
            return
        if s["phase"] == "COLLECT" and time.time() - t0 > grace:
            requests.post(f"{url}/api/v1/fl/round/close-collection")
        time.sleep(0.5)
    raise TimeoutError(f"round {rid} did not finish")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-url", default="http://localhost:8000")
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--clients-per-round", type=int, default=5)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=0.5)
    ap.add_argument("--clip-norm", type=float, default=10.0)
    ap.add_argument("--epsilons", default="none,10,5,1")
    ap.add_argument("--out", default="fl_results.json")
    args = ap.parse_args()

    results = {}
    for tok in args.epsilons.split(","):
        tok = tok.strip()
        eps = None if tok.lower() == "none" else float(tok)
        print(f"\n### sweep target_epsilon = {tok}", flush=True)
        requests.post(f"{args.server_url}/api/v1/fl/experiment/reset")
        time.sleep(5)   # let clients settle before the first round
        for r in range(args.rounds):
            resp = requests.post(f"{args.server_url}/api/v1/fl/round/start", json={
                "clients_per_round": args.clients_per_round,
                "local_epochs": args.local_epochs, "lr": args.lr,
                "clip_norm": args.clip_norm,
                "target_epsilon": eps, "total_rounds_planned": args.rounds,
            }).json()
            wait_done(args.server_url, resp["round_id"])
            h = requests.get(f"{args.server_url}/api/v1/fl/history").json()["rounds"][-1]
            print(f"  r{r+1}: acc={h['test_accuracy']:.4f} "
                  f"eps_spent={h['privacy_spent']['epsilon']}", flush=True)
        results[tok] = requests.get(f"{args.server_url}/api/v1/fl/history").json()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {args.out}")
    print("\n=== summary ===")
    for tok, blk in results.items():
        last = blk["rounds"][-1]
        print(f"  eps={tok:>5}  final_acc={last['test_accuracy']:.4f}  "
              f"eps_spent={last['privacy_spent']['epsilon']}")


if __name__ == "__main__":
    main()
