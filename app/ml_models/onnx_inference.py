"""Real on-device inference via ONNX Runtime.

Same runtime family as ONNX Runtime Mobile, pinned to a single CPU thread so
the measured latency is representative of an edge device. Falls back cleanly
when no model has been exported yet.
"""
import json
import os
import time

import numpy as np

from app.Data_sets.intent.intent_seed import INTENT_LABELS
from fl.data.dataset import encode, tokenize

DEFAULT_MODEL = "deployed_models/intent_model.onnx"


class OnnxIntentClassifier:
    def __init__(self, model_path: str = DEFAULT_MODEL):
        self.model_path = model_path
        self.intents = list(INTENT_LABELS)
        self.available = os.path.exists(model_path)
        self.sess = None
        self.size_kb = 0.0
        if self.available:
            self._load_session()

    def _load_session(self):
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1  # single-core, like a phone
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.sess = ort.InferenceSession(
                self.model_path, opts, providers=["CPUExecutionProvider"]
            )
            self.size_kb = round(os.path.getsize(self.model_path) / 1024, 1)
            self.available = True
        except Exception:
            self.available = False

    def predict(self, query: str) -> tuple[str, float]:
        if not self.available or self.sess is None:
            raise RuntimeError("ONNX model not loaded or available")
        tokens = np.array(encode(query), dtype=np.int64)
        logits = self.sess.run(
            None,
            {"tokens": tokens, "offsets": np.array([0], dtype=np.int64)},
        )[0][0]
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        idx = int(probs.argmax())
        return self.intents[idx], float(probs[idx])

    def explain(self, query: str, top_k: int = 5) -> dict:
        """Occlusion saliency attribution: measures delta in predicted class probability when each token is removed."""
        if not self.available or self.sess is None:
            raise RuntimeError("ONNX model not loaded or available")
        tokens = tokenize(query)
        if not tokens:
            return {
                "method": "occlusion saliency attribution (not SHAP/LIME)",
                "top_tokens": [],
            }

        base_label, base_prob = self.predict(query)
        target_idx = self.intents.index(base_label)

        contributions = []
        for i, tok in enumerate(tokens):
            occluded_tokens = tokens[:i] + tokens[i + 1:]
            occluded_text = " ".join(occluded_tokens)
            if not occluded_tokens:
                occ_tokens = np.array([0], dtype=np.int64)
            else:
                occ_tokens = np.array(encode(occluded_text), dtype=np.int64)

            logits = self.sess.run(
                None,
                {"tokens": occ_tokens, "offsets": np.array([0], dtype=np.int64)},
            )[0][0]
            exp = np.exp(logits - logits.max())
            probs = exp / exp.sum()
            occ_prob = float(probs[target_idx])
            delta = round(base_prob - occ_prob, 4)
            contributions.append({"token": tok, "contribution": delta})

        contributions.sort(key=lambda d: abs(d["contribution"]), reverse=True)
        return {
            "method": "occlusion saliency attribution (not SHAP/LIME)",
            "top_tokens": contributions[:top_k],
        }

    def predict_intent(self, query: str) -> dict:
        t0 = time.perf_counter()
        intent, conf = self.predict(query)
        lat = (time.perf_counter() - t0) * 1000
        return {
            "intent": intent,
            "confidence": round(conf, 4),
            "inference_latency_ms": round(lat, 3),
            "runtime": "ONNX Runtime (CPUExecutionProvider, 1 thread)",
            "model_size_kb": self.size_kb,
            "external_calls": 0,
        }


onnx_classifier = OnnxIntentClassifier()
