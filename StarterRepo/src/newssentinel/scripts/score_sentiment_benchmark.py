from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ..config import settings
from ..enrich.sentiment import FinbertTitleScorer, normalize_dataset_label

DEFAULT_INPUT = Path("artifacts/sentiment/financial_phrasebank_500.csv")
DEFAULT_OUTPUT = Path("artifacts/sentiment/financial_phrasebank_500_finbert.csv")
DEFAULT_METRICS = Path("artifacts/sentiment/financial_phrasebank_500_finbert_metrics.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the Financial PhraseBank benchmark with FinBERT.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--batch-size", type=int, default=settings.FINBERT_BATCH_SIZE)
    args = parser.parse_args()

    from sklearn.metrics import accuracy_score, classification_report

    df = pd.read_csv(args.input)
    if "sentence" not in df.columns or "label" not in df.columns:
        raise ValueError("Benchmark CSV must contain sentence and label columns")

    df["label"] = df["label"].apply(normalize_dataset_label)
    scorer = FinbertTitleScorer(settings.FINBERT_MODEL_NAME)

    results = []
    sentences = [str(sentence).strip() for sentence in df["sentence"].fillna("")]
    for start in range(0, len(sentences), args.batch_size):
        batch = sentences[start : start + args.batch_size]
        for result in scorer.score_batch(batch):
            if result is None:
                results.append(
                    {
                        "pred_label_finbert": None,
                        "p_positive_finbert": None,
                        "p_negative_finbert": None,
                        "p_neutral_finbert": None,
                        "score_finbert": None,
                    }
                )
                continue
            results.append(
                {
                    "pred_label_finbert": result.label,
                    "p_positive_finbert": result.p_positive,
                    "p_negative_finbert": result.p_negative,
                    "p_neutral_finbert": result.p_neutral,
                    "score_finbert": result.score,
                }
            )

    pred_df = pd.DataFrame(results)
    out = pd.concat([df, pred_df], axis=1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    valid = out.dropna(subset=["pred_label_finbert"])
    metrics = {
        "model_name": settings.FINBERT_MODEL_NAME,
        "rows": int(len(out)),
        "scored_rows": int(len(valid)),
        "accuracy": float(accuracy_score(valid["label"], valid["pred_label_finbert"]))
        if not valid.empty
        else None,
        "classification_report": classification_report(
            valid["label"],
            valid["pred_label_finbert"],
            labels=["negative", "neutral", "positive"],
            zero_division=0,
            output_dict=True,
        )
        if not valid.empty
        else {},
    }
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"Saved {args.output}")
    print(f"Saved {args.metrics_output}")
    if metrics["accuracy"] is not None:
        print(f"Accuracy: {metrics['accuracy']:.4f}")


if __name__ == "__main__":
    main()
