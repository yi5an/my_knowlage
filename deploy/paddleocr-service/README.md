# PaddleOCR Service

Internal OCR service for KnowPilot YouTube visual analysis.

## API

`POST /ocr`

Multipart form:

- `image`: JPEG/PNG frame image

Response:

```json
{
  "blocks": [
    {
      "text": "行业轮动思维导图",
      "bbox": [12, 20, 420, 66],
      "confidence": 0.97,
      "reading_order": 1,
      "region_type": null
    }
  ]
}
```

KnowPilot uses the returned text, bounding boxes, confidence, and reading order
to reconstruct PPT, mind-map, chart, and table evidence.

## Local Run

```bash
docker build -t knowpilot-paddleocr ./deploy/paddleocr-service
docker run --rm -p 8866:8866 knowpilot-paddleocr
curl http://localhost:8866/health
```

## Compose Deployment

Keep the service on the private Docker network and point the backend at it:

```env
YOUTUBE_VISUAL_ANALYSIS_ENABLED=true
OCR_BASE_URL=http://paddleocr:8866
```

Do not expose `8866` publicly.
