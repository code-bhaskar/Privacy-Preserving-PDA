"""Single entry point the services use — keeps services free of ML internals."""
from app.ml_models.intent_classifier import intent_classifier
from app.ml_models.entity_extractor import entity_extractor
from app.ml_models.summarizer import local_summarizer


def warm_up() -> None:
    intent_classifier.fit_global()


def classify(text: str):
    return intent_classifier.predict(text)


def explain(text: str, top_k: int = 5):
    return intent_classifier.explain(text, top_k)


def extract(text: str, intent: str):
    return entity_extractor.extract(text, intent)


def summarize(texts: list[str], max_sentences: int = 3) -> str:
    return local_summarizer.summarize(texts, max_sentences)
