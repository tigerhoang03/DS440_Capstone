from datetime import datetime
from types import SimpleNamespace

from newssentinel.enrich.sentiment import FinbertSentiment
from newssentinel.worker import sentiment as sentiment_worker


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        return None


class FakeScorer:
    def __init__(self):
        self.titles = []

    def score_batch(self, titles: list[str]):
        self.titles.extend(titles)
        return [
            FinbertSentiment(
                label="positive",
                score=0.75,
                p_positive=0.80,
                p_negative=0.05,
                p_neutral=0.15,
                model_name="ProsusAI/finbert",
            )
            for _ in titles
        ]


async def test_sentiment_worker_scores_titles_and_updates_rows(monkeypatch):
    rows = [
        SimpleNamespace(id=1, title="Revenue tops estimates", detected_at=datetime.utcnow()),
        SimpleNamespace(id=2, title="Guidance raised", detected_at=datetime.utcnow()),
    ]
    updates = []

    async def fake_list_news_needing_sentiment(session, limit, model_name):
        assert limit == 10
        assert model_name == "finbert"
        return rows

    async def fake_update_news_sentiment(session, item_id, result, model_tag):
        updates.append((item_id, result.label, result.score, model_tag))

    monkeypatch.setattr(sentiment_worker, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(sentiment_worker, "list_news_needing_sentiment", fake_list_news_needing_sentiment)
    monkeypatch.setattr(sentiment_worker, "update_news_sentiment", fake_update_news_sentiment)

    scorer = FakeScorer()
    enriched = await sentiment_worker.run_once(
        scorer,
        limit=10,
        batch_size=1,
        model_tag="finbert",
    )

    assert enriched == 2
    assert scorer.titles == ["Revenue tops estimates", "Guidance raised"]
    assert updates == [
        (1, "positive", 0.75, "finbert"),
        (2, "positive", 0.75, "finbert"),
    ]
