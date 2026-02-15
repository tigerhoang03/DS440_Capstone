# TradingView collector (placeholder)

Possible approaches:
- If credentials allow: alerts/webhooks -> ingest endpoint
- If only the news page: HTML scraping may be blocked; OCR may be required

Recommended:
- If alerts can be delivered via webhook, that is fastest + most reliable.
- If OCR: render page -> capture region -> OCR -> parse -> NormalizedItem

Add:
- `alerts_webhook.py`
- `ocr_pipeline.py`
