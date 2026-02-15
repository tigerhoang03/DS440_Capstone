from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

def vader_compound(text: str | None) -> float | None:
    if not text:
        return None
    return float(_analyzer.polarity_scores(text)["compound"])
