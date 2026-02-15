import re

# Very naive ticker extraction:
# - $TSLA style
# - (TSLA) style
# You should replace with a robust NER + exchange-aware symbol dictionary.
_dollar = re.compile(r"\$([A-Z]{1,6})(?![A-Z])")
_paren = re.compile(r"\(([A-Z]{1,6})\)")

def extract_tickers(text: str | None) -> list[str]:
    if not text:
        return []
    s = text.upper()
    found = set(_dollar.findall(s) + _paren.findall(s))
    return sorted(found)
