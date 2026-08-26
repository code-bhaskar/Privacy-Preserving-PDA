import argparse
import json
import os
import time

from fl.client.agent import FederatedClient, StaleRound


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", type=int, required=True)
    ap.add_argument("--server-url", default="http://localhost:8000")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--rounds", type=int, default=1000)
    ap.add_argument("--drop-at", default=None, choices=[None, "COLLECT"])
    args = ap.parse_args()

    meta_path = os.path.join("fl_data", "meta.json")
    num_classes = json.load(open(meta_path))["num_classes"] \
        if os.path.exists(meta_path) else 7

    data_dir = args.data_dir or f"fl_data/client_{args.client_id}"
    c = FederatedClient(args.client_id, args.server_url, data_dir,
                        num_classes=num_classes, drop_at_phase=args.drop_at)
    print(c.register(), flush=True)
    print(f"[client {args.client_id}] waiting for rounds...", flush=True)

    done = 0
    while done < args.rounds:
        try:
            c.register()   # idempotent; self-heals after a coordinator reset
            if c.run_round():
                done += 1
        except (TimeoutError, StaleRound) as e:
            print(f"[client {args.client_id}] skipping round: {e}", flush=True)
            time.sleep(1)
        except Exception as e:
            print(f"[client {args.client_id}] {type(e).__name__}: {e}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
