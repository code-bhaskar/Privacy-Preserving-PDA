import pytest
from app.Data_sets.intent.intent_seed import INTENT_LABELS
from app.ml_models import model_inference
from app.ml_models.onnx_inference import onnx_classifier


EXPECTED_INTENTS = {
    "SCHEDULE_EVENT",
    "CREATE_REMINDER",
    "GET_EVENTS",
    "GET_REMINDERS",
    "DELETE_EVENT",
    "DELETE_REMINDER",
    "SUMMARIZE_MESSAGES",
    "GREETING",
}


def test_intent_labels_match_dispatcher():
    """Assert the model's label space matches the assistant dispatcher exactly."""
    assert set(INTENT_LABELS) == EXPECTED_INTENTS
    assert set(onnx_classifier.intents) == EXPECTED_INTENTS


def test_onnx_model_availability_and_size():
    assert onnx_classifier.available is True
    assert onnx_classifier.sess is not None
    assert onnx_classifier.size_kb > 0
    assert onnx_classifier.size_kb < 500  # Stays lightweight for on-device


@pytest.mark.parametrize(
    "query,expected_intent",
    [
        ("schedule a meeting with john tomorrow at 10", "SCHEDULE_EVENT"),
        ("remind me to call rahul at 5 pm", "CREATE_REMINDER"),
        ("show me my meetings tomorrow", "GET_EVENTS"),
        ("what reminders do i have", "GET_REMINDERS"),
        ("cancel my meeting with john", "DELETE_EVENT"),
        ("delete my reminder to call rahul", "DELETE_REMINDER"),
        ("summarize my unread messages", "SUMMARIZE_MESSAGES"),
        ("hello assistant", "GREETING"),
    ],
)
def test_all_eight_intents_classified_correctly(query, expected_intent):
    intent, conf = model_inference.classify(query)
    assert intent == expected_intent
    assert conf >= 0.5


def test_onnx_inference_latency():
    res = onnx_classifier.predict_intent("schedule a call with team tomorrow")
    assert res["intent"] == "SCHEDULE_EVENT"
    assert res["inference_latency_ms"] < 25.0  # Ultra-fast local execution
    assert res["external_calls"] == 0


def test_occlusion_saliency_explanation():
    exp = model_inference.explain("remind me to buy milk tomorrow", top_k=3)
    assert "occlusion saliency" in exp["method"]
    assert len(exp["top_tokens"]) > 0
    assert "token" in exp["top_tokens"][0]
    assert "contribution" in exp["top_tokens"][0]


def test_fallback_to_tfidf_when_onnx_unavailable(monkeypatch):
    monkeypatch.setattr(onnx_classifier, "available", False)
    monkeypatch.setattr(onnx_classifier, "sess", None)

    intent, conf = model_inference.classify("hello there")
    assert intent == "GREETING"
    assert conf > 0.0

    exp = model_inference.explain("hello there")
    assert "attribution" in exp["method"]


def test_intent_model_empty_string():
    intent, conf = model_inference.classify("")
    assert isinstance(intent, str)
    assert 0.0 <= conf <= 1.0


def test_intent_model_long_utterance():
    long_text = "could you please schedule a team sync meeting with john and sarah tomorrow morning at 10 am to discuss project status"
    intent, conf = model_inference.classify(long_text)
    assert intent == "SCHEDULE_EVENT"
    assert conf >= 0.5


def test_intent_model_explain_respects_top_k():
    exp = model_inference.explain("please remind me to submit the report tomorrow", top_k=2)
    assert len(exp["top_tokens"]) <= 2
