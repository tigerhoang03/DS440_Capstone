import pytest

from newssentinel.enrich.sentiment import (
    DATASET_LABEL_MAPPING,
    MODEL_LABEL_MAPPING,
    finbert_score_from_probabilities,
    model_label_from_index,
    normalize_dataset_label,
)


def test_dataset_label_mapping_matches_financial_phrasebank_metadata():
    assert DATASET_LABEL_MAPPING == {
        0: "negative",
        1: "neutral",
        2: "positive",
    }
    assert normalize_dataset_label(0) == "negative"
    assert normalize_dataset_label(1) == "neutral"
    assert normalize_dataset_label(2) == "positive"
    assert normalize_dataset_label("Positive") == "positive"


def test_model_label_mapping_matches_prosus_finbert_logits():
    assert MODEL_LABEL_MAPPING == {
        0: "positive",
        1: "negative",
        2: "neutral",
    }
    assert model_label_from_index(0) == "positive"
    assert model_label_from_index(1) == "negative"
    assert model_label_from_index(2) == "neutral"


def test_finbert_score_is_positive_probability_minus_negative_probability():
    result = finbert_score_from_probabilities([0.70, 0.10, 0.20], model_name="ProsusAI/finbert")

    assert result.label == "positive"
    assert result.score == pytest.approx(0.60)
    assert result.p_positive == pytest.approx(0.70)
    assert result.p_negative == pytest.approx(0.10)
    assert result.p_neutral == pytest.approx(0.20)
    assert result.metadata()["model_name"] == "ProsusAI/finbert"
