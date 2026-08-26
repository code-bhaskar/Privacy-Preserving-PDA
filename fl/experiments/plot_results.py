"""Render accuracy-vs-epsilon chart + CSV table from fl_results.json."""
import argparse
import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="fl_results.json")
    ap.add_argument("--png", default="results/accuracy_vs_epsilon.png")
    ap.add_argument("--csv", default="results/metrics_summary.csv")
    args = ap.parse_args()

    import os
    os.makedirs(os.path.dirname(args.png), exist_ok=True)
    data = json.load(open(args.results))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    rows = []
    for tok, blk in data.items():
        rounds = blk["rounds"]
        xs = [r["round_id"] for r in rounds]
        ys = [r["test_accuracy"] for r in rounds]
        label = "no DP (eps=inf)" if tok == "none" else f"eps={tok}"
        ax1.plot(range(1, len(xs) + 1), ys, marker="o", ms=3, label=label)
        last = rounds[-1]
        rows.append({
            "target_epsilon": "inf" if tok == "none" else tok,
            "delta": last["privacy_spent"]["delta"],
            "noise_multiplier": last["noise_multiplier"],
            "final_test_accuracy": last["test_accuracy"],
            "final_test_loss": last["test_loss"],
            "epsilon_spent": last["privacy_spent"]["epsilon"],
            "rounds": len(rounds),
            "bytes_per_client_uplink": last["bytes_per_client_uplink"],
            "total_uplink_bytes": last["total_uplink_bytes"],
        })

    ax1.set_xlabel("Federated round")
    ax1.set_ylabel("Test accuracy (SNIPS held-out)")
    ax1.set_title("Convergence under differential privacy")
    ax1.legend()
    ax1.grid(alpha=0.3)

    finite = [r for r in rows if r["target_epsilon"] != "inf"]
    finite.sort(key=lambda r: float(r["target_epsilon"]))
    if finite:
        ax2.plot([float(r["target_epsilon"]) for r in finite],
                 [r["final_test_accuracy"] for r in finite], marker="s", color="crimson")
    inf_row = [r for r in rows if r["target_epsilon"] == "inf"]
    if inf_row:
        ax2.axhline(inf_row[0]["final_test_accuracy"], ls="--", color="gray",
                    label="no DP (eps=inf)")
        ax2.legend()
    ax2.set_xscale("log")
    ax2.set_xlabel("Privacy budget epsilon (log scale)")
    ax2.set_ylabel("Final test accuracy")
    ax2.set_title("Privacy-utility trade-off")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(args.png, dpi=150)

    with open(args.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {args.png} and {args.csv}")
    for r in rows:
        print(f"  eps={r['target_epsilon']:>5}  acc={r['final_test_accuracy']:.4f}  "
              f"spent={r['epsilon_spent']}")


if __name__ == "__main__":
    main()
