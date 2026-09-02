"""Regression tests for the two ONNX artifacts and the label-space guard.

Background — this is a bug that actually shipped once. ``fl/deploy/export_onnx``
used to write the federated global model straight to
``deployed_models/intent_model.onnx``, which is the artifact
``app/ml_models/onnx_inference.py`` serves for ``POST /assistant/command``.
The federated model is trained on SNIPS (7 intents); the assistant labels
against ``INTENT_LABELS`` (8 intents). ``predict()`` maps ``argmax`` onto
``INTENT_LABELS[i]``, so the assistant did not get slower or less accurate — it
kept returning confident, *wrong* intent names, and nine intent tests went red.

Two guards were added and these tests pin both:

1. Export writes a **separate** federated artifact by default and refuses
   ``--target live`` unless the class counts match.
2. The classifier itself measures the ONNX output width at load time and marks
   the model unavailable (falling back to TF-IDF) rather than mislabelling.
"""
import json

import numpy as np
import pytest

from app.Data_sets.intent.intent_seed import INTENT_LABELS
from fl.deploy import export_onnx
from fl.model.net import IntentNet, flatten_state
from fl.pipeline.supervisor import pipeline_status

SNIPS_CLASSES = 7
ASSISTANT_CLASSES = len(INTENT_LABELS)


def _weights_hex(num_classes: int) -> str:
    """A real, loadable weight vector for an IntentNet with `num_classes` heads."""
    model = IntentNet(num_classes)
    return flatten_state(model.state_dict()).astype(np.float32).tobytes().hex()


@pytest.fixture
def sandbox_paths(tmp_path, monkeypatch):
    """Redirect every artifact path into tmp_path so tests never touch the repo."""
    out = tmp_path / "deployed_models"
    out.mkdir()
    monkeypatch.setattr(export_onnx, "OUT_DIR", str(out))
    monkeypatch.setattr(export_onnx, "LIVE_MODEL", str(out / "intent_model.onnx"))
    monkeypatch.setattr(export_onnx, "LIVE_INT8", str(out / "intent_int8.onnx"))
    monkeypatch.setattr(
        export_onnx, "FEDERATED_MODEL", str(out / "intent_model_federated.onnx"))
    monkeypatch.setattr(
        export_onnx, "FEDERATED_INT8", str(out / "intent_int8_federated.onnx"))
    return out


def test_assistant_label_space_is_eight_classes():
    """The guard's reference point. If this changes, export/live must change too."""
    assert ASSISTANT_CLASSES == 8
    assert ASSISTANT_CLASSES != SNIPS_CLASSES


def test_default_export_writes_the_federated_artifact_only(sandbox_paths):
    sizes = export_onnx.export(_weights_hex(SNIPS_CLASSES), SNIPS_CLASSES)

    assert sizes["target"] == "federated"
    assert sizes["num_classes"] == SNIPS_CLASSES
    assert sizes["served_by_assistant"] is False

    assert (sandbox_paths / "intent_model_federated.onnx").exists()
    assert (sandbox_paths / "intent_int8_federated.onnx").exists()
    # The regression: this used to be written by the default export.
    assert not (sandbox_paths / "intent_model.onnx").exists()
    assert not (sandbox_paths / "intent_int8.onnx").exists()


def test_default_export_writes_a_federated_model_card(sandbox_paths):
    export_onnx.export(_weights_hex(SNIPS_CLASSES), SNIPS_CLASSES)

    card = json.loads((sandbox_paths / "model_card_federated.json").read_text())
    assert card["target"] == "federated"
    assert card["num_classes"] == SNIPS_CLASSES
    assert card["onnx_fp32_kb"] > 0
    assert card["compression_ratio"] >= 1.0
    # The live card must not be produced by a federated export.
    assert not (sandbox_paths / "model_card.json").exists()


def test_live_export_refuses_a_mismatched_label_space(sandbox_paths):
    """The exact mistake that broke the assistant, now rejected."""
    with pytest.raises(ValueError) as exc:
        export_onnx.export(
            _weights_hex(SNIPS_CLASSES), SNIPS_CLASSES, target="live")

    msg = str(exc.value)
    assert "refusing to overwrite the served assistant model" in msg
    assert str(SNIPS_CLASSES) in msg and str(ASSISTANT_CLASSES) in msg
    assert not (sandbox_paths / "intent_model.onnx").exists()


def test_live_export_is_allowed_when_the_label_spaces_agree(sandbox_paths):
    sizes = export_onnx.export(
        _weights_hex(ASSISTANT_CLASSES), ASSISTANT_CLASSES, target="live")

    assert sizes["served_by_assistant"] is True
    assert (sandbox_paths / "intent_model.onnx").exists()
    assert (sandbox_paths / "intent_int8.onnx").exists()
    # A live export must not also drop a federated artifact next to it.
    assert not (sandbox_paths / "intent_model_federated.onnx").exists()


def test_unknown_export_target_is_rejected(sandbox_paths):
    with pytest.raises(ValueError, match="target must be"):
        export_onnx.export(
            _weights_hex(SNIPS_CLASSES), SNIPS_CLASSES, target="production")


def test_classifier_rejects_a_model_with_the_wrong_output_width(sandbox_paths):
    """Guard 2: a wrong-width artifact must not be served at all."""
    from app.ml_models.onnx_inference import OnnxIntentClassifier

    export_onnx.export(_weights_hex(SNIPS_CLASSES), SNIPS_CLASSES)
    clf = OnnxIntentClassifier(str(sandbox_paths / "intent_model_federated.onnx"))

    assert clf.available is False
    assert clf.sess is None
    assert clf.mismatch == {
        "model_classes": SNIPS_CLASSES,
        "assistant_classes": ASSISTANT_CLASSES,
    }
    with pytest.raises(RuntimeError):
        clf.predict("schedule a meeting tomorrow")


def test_classifier_accepts_a_matching_width_model(sandbox_paths):
    from app.ml_models.onnx_inference import OnnxIntentClassifier

    export_onnx.export(
        _weights_hex(ASSISTANT_CLASSES), ASSISTANT_CLASSES, target="live")
    clf = OnnxIntentClassifier(str(sandbox_paths / "intent_model.onnx"))

    assert clf.available is True, clf.mismatch
    assert clf.sess is not None
    assert clf.mismatch is None
    assert clf.size_kb > 0
    intent, conf = clf.predict("schedule a meeting tomorrow")
    # Weights are random, so the label is arbitrary — but it must be a real
    # assistant intent, never an index-mapped SNIPS label.
    assert intent in INTENT_LABELS
    assert 0.0 <= conf <= 1.0


def test_classifier_without_an_artifact_falls_back_cleanly(tmp_path):
    from app.ml_models.onnx_inference import OnnxIntentClassifier

    clf = OnnxIntentClassifier(str(tmp_path / "does_not_exist.onnx"))
    assert clf.available is False
    assert clf.mismatch is None  # absent != mislabelled
    with pytest.raises(RuntimeError):
        clf.predict("hello")


def test_served_classifier_is_loaded_with_the_assistant_label_space():
    """The model the running app actually serves must be the 8-class one."""
    from app.ml_models.onnx_inference import onnx_classifier

    assert onnx_classifier.mismatch is None, (
        f"served model disagrees with INTENT_LABELS: {onnx_classifier.mismatch}"
    )
    assert onnx_classifier.available is True
    assert onnx_classifier.intents == list(INTENT_LABELS)
    assert onnx_classifier.predict_intent("remind me to call Sai")["intent"] in INTENT_LABELS


def test_pipeline_status_exposes_both_artifacts_and_their_class_counts():
    """The UI reads these to show why export never overwrites the live model."""
    status = pipeline_status()

    assert status["onnx_artifact"].endswith("intent_model_federated.onnx")
    assert status["live_model_artifact"].endswith("intent_model.onnx")
    assert status["onnx_artifact"] != status["live_model_artifact"]
    assert status["federated_model_classes"] == SNIPS_CLASSES
    assert status["live_model_classes"] == ASSISTANT_CLASSES
    assert status["live_model_artifact_exists"] is True

    artifacts = status["artifacts"]
    for key in ("federated_onnx", "federated_int8", "live_onnx",
                "benchmark", "model_card", "export_log"):
        assert key in artifacts, f"missing artifact key {key!r}"
    assert artifacts["federated_onnx"].endswith("intent_model_federated.onnx")
    assert artifacts["model_card"].endswith("model_card_federated.json")


def test_pipeline_export_service_refuses_without_an_aggregated_model(monkeypatch):
    from app.core.exceptions import ValidationError
    from app.services import pipeline_service

    monkeypatch.setattr(pipeline_service, "coordinator_has_model", lambda: False)
    with pytest.raises(ValidationError, match="No aggregated global model"):
        pipeline_service.pipeline_service.export_onnx(db=None, benchmark=False)
