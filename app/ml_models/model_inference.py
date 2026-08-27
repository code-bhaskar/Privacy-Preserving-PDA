"""Single entry point the services use — keeps services free of ML internals."""
from app.ml_models.intent_classifier import intent_classifier
from app.ml_models.onnx_inference import onnx_classifier
from app.ml_models.entity_extractor import entity_extractor
from app.ml_models.summarizer import local_summarizer


def warm_up() -> None:
    intent_classifier.fit_global()
    if onnx_classifier.available and onnx_classifier.sess is None:
        onnx_classifier._load_session()


def classify(text: str) -> tuple[str, float]:
    if onnx_classifier.available and onnx_classifier.sess is not None:
        try:
            return onnx_classifier.predict(text)
        except Exception:
            pass
    return intent_classifier.predict(text)


def explain(text: str, top_k: int = 5) -> dict:
    if onnx_classifier.available and onnx_classifier.sess is not None:
        try:
            return onnx_classifier.explain(text, top_k)
        except Exception:
            pass
    return intent_classifier.explain(text, top_k)


def extract(text: str, intent: str):
    return entity_extractor.extract(text, intent)


def summarize(texts: list[str], max_sentences: int = 3) -> str:
    return local_summarizer.summarize(texts, max_sentences)
