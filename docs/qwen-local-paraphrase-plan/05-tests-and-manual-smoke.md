# Phase 05 - Tests And Manual Smoke

## Unit Tests

Add tests for the local provider without loading Qwen.

Use a fake Llama object that returns controlled `create_chat_completion()` payloads.

Required cases:

- Parses valid JSON:
  ```json
  {"candidates":[{"stem":"..."}]}
  ```
- Extracts JSON from surrounding text.
- Rejects malformed JSON after retry.
- Filters candidate equal to source.
- Filters duplicate candidates.
- Preserves protected terms such as `ABC`, `SpO2`, `mmHg`, `GCS`.
- Retries once when required protected terms are missing.
- Raises `AppError(GENERATION_FAILED)` when no candidate survives.

## Integration Tests

Use dependency/config overrides and monkeypatching so tests never download the real model.

Required cases:

- `POST /paraphrase-jobs` with `provider=local` creates a job and candidates using fake Qwen.
- Payload without provider uses `PARAPHRASE_PROVIDER=local`.
- `provider=api` returns 503 and persists a `FAILED` job without making HTTP calls.
- Existing `provider=mock` e2e tests still pass.
- `/questions/{id}` HTML contains local provider in the generated request script.
- `/config/public` includes `paraphraseProvider`.

## Regression Tests

Run:

```powershell
python -m pytest -q
```

Expected:

- No test downloads Qwen.
- No test calls DeepSeek.
- Existing E5 validation tests still use `mock_deterministic` embedding provider.
- Document generation tests remain on `mock` or their explicit fake API generator.

## Manual Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Set `.env`:

```env
PARAPHRASE_PROVIDER=local
LOCAL_PARAPHRASE_MODEL_REPO_ID=Qwen/Qwen2.5-1.5B-Instruct-GGUF
LOCAL_PARAPHRASE_MODEL_FILENAME=qwen2.5-1.5b-instruct-q4_k_m.gguf
LOCAL_PARAPHRASE_CONTEXT_TOKENS=2048
LOCAL_PARAPHRASE_MAX_TOKENS=512
LOCAL_PARAPHRASE_TEMPERATURE=0.35
LOCAL_PARAPHRASE_TOP_P=0.9
LOCAL_PARAPHRASE_REPEAT_PENALTY=1.05
LOCAL_PARAPHRASE_THREADS=0
LOCAL_PARAPHRASE_GPU_LAYERS=0
```

Run app:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

First paraphrase request should download the GGUF model from Hugging Face. Later requests should use the local cache.

## Manual Smoke Scenarios

Use seeded questions and a hospital-style question with mixed Vietnamese/English terms.

Scenario 1:

- Source contains `ABC`.
- Generate 3 paraphrases.
- Confirm all candidate stems still contain `ABC` or the exact required protected term.
- Validate job.
- Approve one candidate.
- Save as child question.

Scenario 2:

- Source contains `SpO2` and `mmHg`.
- Generate paraphrases.
- Confirm neither term is dropped or rewritten.
- Validate warnings and scores.

Scenario 3:

- Temporarily set an invalid model filename.
- Create local paraphrase job.
- Confirm response is 503.
- Confirm job detail shows `FAILED`.

## Acceptance Criteria

- Laptop with 8-16 GB RAM can generate a small batch of paraphrases without external API calls.
- First request may be slow due to model download/load; app startup remains fast.
- Candidate quality is good enough for E5 validation and human review.
- All automated tests pass without model download.
