"""Latency benchmark for the exported on-device model (PRD FR-19)."""
import json

import numpy as np

from app.ml_models.onnx_inference import onnx_classifier

QUERIES = [
    "play some jazz",
    "what's the weather in paris tomorrow",
    "book a table for four at eight",
    "add this song to my workout playlist",
    "rate the current book five stars",
    "find showtimes for the new movie nearby",
]


def main(iters: int = 200):
    lat = []
    for _ in range(iters):
        for q in QUERIES:
            lat.append(onnx_classifier.predict_intent(q)["inference_latency_ms"])
    out = {
        "samples": len(lat),
        "p50_ms": round(float(np.percentile(lat, 50)), 4),
        "p95_ms": round(float(np.percentile(lat, 95)), 4),
        "p99_ms": round(float(np.percentile(lat, 99)), 4),
        "model_size_kb": onnx_classifier.size_kb,
        "runtime": "ONNX Runtime CPUExecutionProvider, 1 intra-op thread",
    }
    print(json.dumps(out, indent=2))
    with open("deployed_models/benchmark.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
