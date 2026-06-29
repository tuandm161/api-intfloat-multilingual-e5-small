# Phase 04 - API And UI Integration

## Provider Selection

Update paraphrase job creation so it uses `settings.paraphrase_provider` as the default provider.

Rules:

- If request payload explicitly includes `provider`, honor it.
- If request payload omits `provider`, use `settings.paraphrase_provider`.
- Keep `mock` available for tests and quick demos.
- Treat `api` as disabled for paraphrase in this phase.

Implementation target:

- Change `ParaphraseJobCreate.provider` from hardcoded default `mock` to optional.
- In `ParaphraseService.create_job()`, resolve:

```python
provider = payload.provider or settings.paraphrase_provider
```

## UI Changes

Question detail page currently sends:

```javascript
provider: '{{ generation_provider or "mock" }}'
```

Change it to use the paraphrase provider:

```javascript
provider: '{{ paraphrase_provider or "local" }}'
```

Route context change:

- Pass `paraphrase_provider=settings.paraphrase_provider.value`.
- Keep `generation_provider` only if still needed elsewhere.

## Public Config

`GET /config/public` should include:

```json
{
  "paraphraseProvider": "local"
}
```

Existing safe fields remain unchanged.

## API Compatibility

Do not change endpoint paths:

- `POST /paraphrase-jobs`
- `GET /paraphrase-jobs/{job_id}`
- `POST /paraphrase-jobs/{job_id}/validate`
- Candidate approve/reject/save endpoints

Do not change response shape:

```json
{
  "success": true,
  "data": {
    "jobId": "...",
    "status": "GENERATED",
    "candidateCount": 3
  },
  "error": null
}
```

## Document Generation

Do not route document generation to Qwen in this phase.

Keep current behavior:

- `GENERATION_PROVIDER=mock` uses `MockDocumentQuestionGenerator`.
- `GENERATION_PROVIDER=api` uses DeepSeek document generation if API key is configured.

## Database

No schema migration is required.

Existing fields are enough:

- `paraphrase_jobs.provider`
- `paraphrase_jobs.status`
- `paraphrase_candidates.candidate_stem`
- validation score fields
- warnings/status/reviewer notes
