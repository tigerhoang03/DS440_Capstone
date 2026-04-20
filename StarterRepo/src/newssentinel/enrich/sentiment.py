from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

DATASET_LABEL_MAPPING = {
    0: "negative",
    1: "neutral",
    2: "positive",
}

MODEL_LABEL_MAPPING = {
    0: "positive",
    1: "negative",
    2: "neutral",
}


@dataclass(frozen=True)
class FinbertSentiment:
    label: str
    score: float
    p_positive: float
    p_negative: float
    p_neutral: float
    model_name: str

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


def vader_compound(text: str | None) -> float | None:
    if not text:
        return None
    return float(_analyzer.polarity_scores(text)["compound"])


def normalize_dataset_label(label: int | str) -> str:
    if isinstance(label, str):
        normalized = label.strip().lower()
        if normalized in {"positive", "negative", "neutral"}:
            return normalized
        if normalized.isdigit():
            label = int(normalized)
        else:
            raise ValueError(f"Unsupported dataset label: {label!r}")
    try:
        return DATASET_LABEL_MAPPING[int(label)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported dataset label: {label!r}") from exc


def model_label_from_index(index: int) -> str:
    try:
        return MODEL_LABEL_MAPPING[int(index)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported FinBERT model label index: {index!r}") from exc


def finbert_score_from_probabilities(
    probabilities: list[float] | tuple[float, float, float],
    model_name: str,
) -> FinbertSentiment:
    if len(probabilities) != 3:
        raise ValueError("FinBERT probabilities must contain exactly 3 values")

    p_positive = float(probabilities[0])
    p_negative = float(probabilities[1])
    p_neutral = float(probabilities[2])
    best_index = max(range(3), key=lambda idx: float(probabilities[idx]))

    return FinbertSentiment(
        label=model_label_from_index(best_index),
        score=p_positive - p_negative,
        p_positive=p_positive,
        p_negative=p_negative,
        p_neutral=p_neutral,
        model_name=model_name,
    )


class FinbertTitleScorer:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._tokenizer = None
        self._model = None

    def _load(self):
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

        # Lazy imports keep the normal dashboard/API import path lightweight.
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        return tokenizer, model

    def score_batch(self, titles: list[str]) -> list[FinbertSentiment | None]:
        clean_titles = [title.strip() if title else "" for title in titles]
        if not clean_titles:
            return []

        tokenizer, model = self._load()

        import torch
        import torch.nn.functional as functional

        non_empty_positions = [idx for idx, title in enumerate(clean_titles) if title]
        if not non_empty_positions:
            return [None for _ in clean_titles]

        non_empty_titles = [clean_titles[idx] for idx in non_empty_positions]
        inputs = tokenizer(
            non_empty_titles,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        )

        with torch.no_grad():
            outputs = model(**inputs)
            probs_batch = functional.softmax(outputs.logits, dim=-1).tolist()

        scored: list[FinbertSentiment | None] = [None for _ in clean_titles]
        for position, probs in zip(non_empty_positions, probs_batch, strict=True):
            scored[position] = finbert_score_from_probabilities(probs, model_name=self.model_name)
        return scored
