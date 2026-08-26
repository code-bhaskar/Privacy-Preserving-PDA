"""Export the federated-trained model to ONNX + INT8 for on-device deployment.

    python -m fl.deploy.export_onnx --server-url http://localhost:8000
"""
import argparse
import json
import os

import numpy as np
import torch

from fl.model.net import IntentNet, unflatten_state

OUT_DIR = "deployed_models"


def export(weights_hex: str, num_classes: int = 7) -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    model = IntentNet(num_classes)
    flat = np.frombuffer(bytes.fromhex(weights_hex), dtype=np.float32).copy()
    model.load_state_dict(unflatten_state(flat, model.state_dict()))
    model.eval()

    fp32 = f"{OUT_DIR}/intent_fp32.onnx"
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
    )

    # INT8 dynamic quantization - the step that makes it phone-deployable
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = f"{OUT_DIR}/intent_int8.onnx"
    quantize_dynamic(fp32, int8, weight_type=QuantType.QUInt8)

    sizes = {
        "pytorch_params": int(sum(p.numel() for p in model.state_dict().values())),
        "onnx_fp32_kb": round(os.path.getsize(fp32) / 1024, 1),
        "onnx_int8_kb": round(os.path.getsize(int8) / 1024, 1),
    }
    sizes["compression_ratio"] = round(sizes["onnx_fp32_kb"] / sizes["onnx_int8_kb"], 2)
    with open(f"{OUT_DIR}/model_card.json", "w") as f:
        json.dump(sizes, f, indent=2)
    print(json.dumps(sizes, indent=2))
    return sizes


if __name__ == "__main__":
    import requests
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-url", default="http://localhost:8000")
    a = ap.parse_args()
    meta = "fl_data/meta.json"
    nc = json.load(open(meta))["num_classes"] if os.path.exists(meta) else 7
    w = requests.get(f"{a.server_url}/api/v1/fl/model/weights").json()
    export(w["weights_hex"], nc)
