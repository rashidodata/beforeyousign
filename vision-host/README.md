# BeforeYouSign hosted SmolVLM2-500M

## Design

Do **not** put model-weight files in the Redis/Postgres database. Store them in
persistent model/object storage (or a mounted cache) and serve them from a
dedicated inference process on a GPU instance. Redis only stores report status,
locks, usage budgets and cached **one-per-property visual summaries**.

The main BeforeYouSign Render web service is currently a free CPU plan. It does
not run the model. The application uses a protected, operator-configured HTTPS
vLLM-compatible endpoint and never exposes its bearer token to browsers.

## Provision a GPU service

Deploy a protected inference endpoint running the Apache-2.0 model:
`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`. See the official model card:
https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct

One example command on a GPU host with `vllm` installed:

```bash
export HF_HOME=/data/huggingface
vllm serve HuggingFaceTB/SmolVLM2-500M-Video-Instruct \
  --host 0.0.0.0 --port 8000 \
  --api-key "$BYS_VISION_API_TOKEN" \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image": 4}'
```

Put the service behind HTTPS and configure a private authentication key. Mount
persistent storage at `/data/huggingface` (or equivalent); the weights are
cached there and aren't repeatedly redownloaded. Check the vLLM version and
compatible model options before production use.

If using a managed GPU endpoint, ensure it accepts OpenAI-compatible
`POST /v1/chat/completions` with base64 `image_url` messages and one text-only
synthesis call. Test both modes before setting live deployment flags.

## Configure the existing Render web API

In the Render Environment tab for `beforeyousign-api`, configure:

```
BYS_VISION_API_URL=https://YOUR-PRIVATE-GPU-SERVICE/v1/chat/completions
BYS_VISION_API_TOKEN=YOUR_PRIVATE_GPU_API_TOKEN
BYS_VISION_MODEL=HuggingFaceTB/SmolVLM2-500M-Video-Instruct
BYS_VISION_AUTORUN_ENABLED=1
BYS_VISION_DAILY_LIMIT=20
```

Keep all keys private; do not insert them in GitHub Pages JavaScript. `BYS_REDIS_URL`
must already be configured for caching/deduplication.

**Do not set `BYS_VISION_AUTORUN_ENABLED=1` until the endpoint's pricing,
request limits and rights to use listing photographs have been reviewed.**

## Runtime behavior

1. A user imports an Idealista listing using the existing OpenData integration.
2. The browser automatically calls `POST /api/listings/visual-summary` with the
   preview code. No extra OpenData request happens.
3. The backend checks a Redis cache key based on the listing ID and image paths.
4. An uncached report is queued on the single-instance private pilot. Images are
   downloaded from allowlisted Idealista CDN URLs, EXIF is stripped, each image
   is resized and sent to the configured model service in groups of four.
5. The model combines internal batch notes into one Spanish and one English
   property-level summary, with strengths, visible concerns and landlord
   questions. The UI never displays per-photo reports.
6. The website polls status and displays the result. If one or more images
   cannot be fetched, it displays the processed count and labels the result
   partial. Reports are cached for seven days.

The pilot uses FastAPI `BackgroundTasks`; before scaling to multiple instances
or promising durable delivery, move jobs into a proper Redis queue with a
separate worker, retries and monitoring. Automatic inference on every listing
is a potentially significant GPU cost, even though the model weights are open.