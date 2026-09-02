"""Export the federated-trained model to ONNX + INT8 for on-device deployment.

    python -m fl.deploy.export_onnx                       # -> federated artifact
    python -m fl.deploy.export_onnx --target live         # -> the served model

Two artifacts, deliberately kept apart:

``intent_model_federated.onnx`` (default)
    The global model produced by the secure-aggregation rounds. It is trained on
    the **SNIPS** corpus, i.e. 7 intents, and it is what the FL demo measures.

``intent_model.onnx`` (``--target live``)
    The artifact ``app/ml_models/onnx_inference.py`` actually serves for
    ``POST /api/v1/assistant/command``. Its label space is
    ``app.Data_sets.intent.intent_seed.INTENT_LABELS`` — the 8 assistant intents.

Overwriting the live artifact with a SNIPS model does not merely lose accuracy:
``predict()`` maps ``argmax`` onto ``INTENT_LABELS[i]``, so a 7-class model would
confidently return the *wrong intent names*. `--target live` therefore refuses
unless the class counts match.
"""
import argparse
import json
import os

import numpy as np
import torch

from fl.model.net import IntentNet, unflatten_state

OUT_DIR = "deployed_models"

LIVE_MODEL = f"{OUT_DIR}/intent_model.onnx"
LIVE_INT8 = f"{OUT_DIR}/intent_int8.onnx"
FEDERATED_MODEL = f"{OUT_DIR}/intent_model_federated.onnx"
FEDERATED_INT8 = f"{OUT_DIR}/intent_int8_federated.onnx"


def _assistant_class_count() -> int:
    from app.Data_sets.intent.intent_seed import INTENT_LABELS
    return len(INTENT_LABELS)


def export(weights_hex: str, num_classes: int = 7, target: str = "federated") -> dict:
    if target not in ("federated", "live"):
        raise ValueError(f"target must be 'federated' or 'live', got {target!r}")

    if target == "live":
        assistant_classes = _assistant_class_count()
        if num_classes != assistant_classes:
            raise ValueError(
                f"refusing to overwrite the served assistant model: the federated "
                f"model has {num_classes} classes but INTENT_LABELS has "
                f"{assistant_classes}. Serving it would mislabel every intent. "
                f"Export with --target federated, or federate on the assistant's "
                f"own label space first."
            )
        fp32, int8 = LIVE_MODEL, LIVE_INT8
    else:
        fp32, int8 = FEDERATED_MODEL, FEDERATED_INT8

    os.makedirs(OUT_DIR, exist_ok=True)
    model = IntentNet(num_classes)
    flat = np.frombuffer(bytes.fromhex(weights_hex), dtype=np.float32).copy()
    model.load_state_dict(unflatten_state(flat, model.state_dict()))
    model.eval()

    torch.onnx.export(
        model,
        (torch.tensor([1, 2, 3], dtype=torch.long),
         torch.tensor([0], dtype=torch.long)),
        fp32,
        input_names=["tokens", "offsets"],
        output_names=["logits"],
        dynamic_axes={"tokens": {0: "n_tok"}, "offsets": {0: "batch"}},
        opset_version=14,
        dynamo=False,
        # Keep weights inline so there is no separate "*.onnx.data" sidecar
        # file that must be committed alongside the model.
        external_data=False,
    )

    # INT8 dynamic quantization - the step that makes it phone-deployable
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(fp32, int8, weight_type=QuantType.QUInt8)

    sizes = {
        "target": target,
        "num_classes": num_classes,
        "served_by_assistant": target == "live",
        "onnx_path": fp32,
        "int8_path": int8,
        "pytorch_params": int(sum(p.numel() for p in model.state_dict().values())),
        "onnx_fp32_kb": round(os.path.getsize(fp32) / 1024, 1),
        "onnx_int8_kb": round(os.path.getsize(int8) / 1024, 1),
    }
    sizes["compression_ratio"] = round(sizes["onnx_fp32_kb"] / sizes["onnx_int8_kb"], 2)

    card = f"{OUT_DIR}/model_card{'_federated' if target != 'live' else ''}.json"
    with open(card, "w") as f:
        json.dump(sizes, f, indent=2)
    sizes["model_card"] = card
    print(json.dumps(sizes, indent=2))
    return sizes


if __name__ == "__main__":
    import requests
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-url", default="http://localhost:8000")
    ap.add_argument("--target", default="federated", choices=["federated", "live"],
                    help="'federated' (default) writes a separate artifact; 'live' "
                         "overwrites the model the assistant serves and is refused "
                         "unless the class counts match.")
    a = ap.parse_args()
    meta = "fl_data/meta.json"
    nc = json.load(open(meta))["num_classes"] if os.path.exists(meta) else 7
    w = requests.get(f"{a.server_url}/api/v1/fl/model/weights").json()
    export(w["weights_hex"], nc, target=a.target)
