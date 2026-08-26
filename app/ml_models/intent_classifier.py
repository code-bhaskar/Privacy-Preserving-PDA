import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from app.Data_sets.intent.intent_seed import INTENT_DATA, INTENT_LABELS


class IntentClassifier:
    """
    TF-IDF + linear SGD (log-loss).
    Chosen for the PRD's 'lightweight enough for on-device' portability goal
    and because linear weights give free token-level explanations (FR-17).
    The vectorizer is treated as part of the *global* model, so every federated
    client produces a coefficient vector of identical shape.
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), min_df=1, sublinear_tf=True, lowercase=True
        )
        self.classes = np.array(INTENT_LABELS)
        self.model: SGDClassifier | None = None
        self._trained = False

    # ---------- training ----------
    def fit_global(self, data: list[tuple[str, str]] | None = None) -> None:
        data = data or INTENT_DATA
        X_text = [t for t, _ in data]
        y = np.array([l for _, l in data])
        X = self.vectorizer.fit_transform(X_text)
        self.model = SGDClassifier(loss="log_loss", alpha=1e-4, max_iter=1500,
                                   tol=1e-4, random_state=42)
        self.model.fit(X, y)
        self._trained = True

    # ---------- inference (FR-4) ----------
    def predict(self, text: str) -> tuple[str, float]:
        if not self._trained:
            self.fit_global()
        X = self.vectorizer.transform([text])
        proba = self.model.predict_proba(X)[0]
        idx = int(np.argmax(proba))
        return str(self.model.classes_[idx]), float(proba[idx])

    # ---------- explainability (FR-17) ----------
    def explain(self, text: str, top_k: int = 5) -> dict:
        if not self._trained:
            self.fit_global()
        X = self.vectorizer.transform([text])
        label, _ = self.predict(text)
        cls_idx = list(self.model.classes_).index(label)
        coefs = self.model.coef_[cls_idx]
        feats = self.vectorizer.get_feature_names_out()
        present = X.nonzero()[1]
        contribs = [
            {"token": feats[i], "contribution": round(float(coefs[i] * X[0, i]), 4)}
            for i in present
        ]
        contribs.sort(key=lambda d: abs(d["contribution"]), reverse=True)
        return {
            "method": "linear-coefficient attribution (LIME-compatible surrogate)",
            "top_tokens": contribs[:top_k],
        }

    # ---------- federated hooks ----------
    def vector_dim(self) -> int:
        return self.model.coef_.size + self.model.intercept_.size

    def get_weights(self) -> np.ndarray:
        return np.concatenate([self.model.coef_.ravel(), self.model.intercept_.ravel()])

    def set_weights(self, vec: np.ndarray) -> None:
        n_coef = self.model.coef_.size
        self.model.coef_ = vec[:n_coef].reshape(self.model.coef_.shape)
        self.model.intercept_ = vec[n_coef:].reshape(self.model.intercept_.shape)

    def transform(self, texts: list[str]):
        return self.vectorizer.transform(texts)


intent_classifier = IntentClassifier()
