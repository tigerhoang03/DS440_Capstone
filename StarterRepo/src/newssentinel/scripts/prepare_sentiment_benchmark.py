from __future__ import annotations

import argparse
from pathlib import Path

from ..enrich.sentiment import normalize_dataset_label

DEFAULT_OUTPUT = Path("artifacts/sentiment/financial_phrasebank_500.csv")
DATASET_NAME = "takala/financial_phrasebank"
DATASET_CONFIG = "sentences_allagree"
RANDOM_SEED = 42
SAMPLE_SIZE = 500


def _load_phrasebank():
    from datasets import load_dataset

    try:
        return load_dataset(DATASET_NAME, DATASET_CONFIG, trust_remote_code=True)["train"]
    except TypeError:
        return load_dataset(DATASET_NAME, DATASET_CONFIG)["train"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a reproducible 500-row Financial PhraseBank benchmark sample."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    ds = _load_phrasebank()
    df = ds.to_pandas()
    df["label"] = df["label"].apply(normalize_dataset_label)

    sample = df.sample(n=args.sample_size, random_state=args.seed).reset_index(drop=True)
    sample.insert(0, "article_id", range(1, len(sample) + 1))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.output, index=False)

    print(f"Saved {args.output}")
    print(sample["label"].value_counts())


if __name__ == "__main__":
    main()
