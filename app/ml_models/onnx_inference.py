"""Real on-device inference via ONNX Runtime.

Same runtime family as ONNX Runtime Mobile, pinned to a single CPU thread so
the measured latency is representative of an edge device. Falls back cleanly
when no model has been exported yet.
"""
import json
import os
import time

import numpy as np

from fl.data.dataset import encode

DEFAULT_MODEL = "deployed_models/intent_int8.onnx"
META = "fl_data/meta.json"

FALLBACK_INTENTS = ["AddToPlaylist", "BookRestaurant", "GetWeather", "PlayMusic",
                    "RateBook", "SearchCreativeWork", "SearchScreeningEvent"]


def _intents():
    if os.path.exists(META):
        return json.load(open(META))["intents"]
    return FALLBACK_INTENTS


class OnnxIntentClassifier:
    def __init__(self, model_path: str = DEFAULT_MODEL):
        self.model_path = model_path
        self.intents = _intents()
        self.available = os.path.exists(model_path)
        if self.available:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1          # single-core, like a phone
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.sess = ort.InferenceSession(model_path, opts,
                                             providers=["CPUExecutionProvider"])
            self.size_kb = round(os.path.getsize(model_path) / 1024, 1)

    def predict_intent(self, query: str) -> dict:
        if not self.available:
            raise RuntimeError(
                "ONNX model not exported yet - run: python -m fl.deploy.export_onnx")
        t0 = time.perf_counter()
        tokens = np.array(encode(query), dtype=np.int64)
        logits = self.sess.run(None, {"tokens": tokens,
                                      "offsets": np.array([0], dtype=np.int64)})[0][0]
        latency_ms = (time.perf_counter() - t0) * 1000

        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        idx = int(probs.argmax())
        return {
            "intent": self.intents[idx],
            "confidence": float(probs[idx]),
            "inference_latency_ms": round(latency_ms, 3),
            "runtime": "ONNX Runtime (CPUExecutionProvider, 1 thread)",
            "model_size_kb": self.size_kb,
            "external_calls": 0,
        }


onnx_classifier = OnnxIntentClassifier()
