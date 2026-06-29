# Phase 02 - Local Generator

## Target File

Replace the stub in `app/modules/paraphrase/providers/local.py` with a real Qwen GGUF generator.

## Generator Responsibilities

`LocalParaphraseGenerator.generate_stem_paraphrases()` must:

- Receive the existing `GenerateRequest`.
- Load Qwen lazily from Hugging Face/cache.
- Build a strict JSON-only chat prompt.
- Call `llama_cpp.Llama.create_chat_completion()`.
- Parse candidate stems from JSON.
- Return `list[str]` with at most `requested_count` stems.

## Model Loading

Use `Llama.from_pretrained()`:

```python
Llama.from_pretrained(
    repo_id=settings.local_paraphrase_model_repo_id,
    filename=settings.local_paraphrase_model_filename,
    n_ctx=settings.local_paraphrase_context_tokens,
    n_threads=settings.local_paraphrase_threads or None,
    n_gpu_layers=settings.local_paraphrase_gpu_layers,
    verbose=False,
)
```

Implementation rules:

- Wrap import errors in `AppError(ErrorCode.GENERATION_FAILED, ...)`.
- Wrap model download/load errors in `AppError(..., status_code=503)`.
- Cache the loaded model by the config tuple `(repo_id, filename, n_ctx, threads, gpu_layers)`.
- Do not load the model in app startup.
- Do not load the model in tests unless the test explicitly injects a fake loader.

## Prompt Contract

System message:

```text
Bạn là trợ lý tạo câu hỏi điều dưỡng/y khoa an toàn.
Luôn trả về JSON hợp lệ, không thêm chữ ngoài JSON.
Không tự thêm kiến thức y khoa mới.
```

User message must include:

- Original stem.
- Options for context only.
- Correct answer for safety context only.
- Requested count.
- Target language.
- Change strength.
- JSON schema: `{"candidates":[{"stem":"..."}]}`

Rules in the prompt:

- Rewrite only the question stem.
- Do not answer the question.
- Do not alter the correct medical meaning.
- Do not make the correct answer obvious.
- Keep all English medical terms, abbreviations, numbers, and units from the original stem unchanged.
- Do not rewrite options.
- Return JSON only.

## Output Parsing

Parse in this order:

1. Try `json.loads(raw_content)`.
2. If that fails, extract substring from the first `{` to the last `}` and parse again.
3. Require a top-level object with `candidates` list.
4. For each item, accept only dicts with non-empty string `stem`.
5. If no valid stem exists, raise `AppError(ErrorCode.GENERATION_FAILED, ...)`.

## API Disable Behavior

Do not delete `ApiParaphraseGenerator`, but update paraphrase provider routing so `GenerationProvider.api` for paraphrase returns a 503 failure without making an HTTP request.

The failure should still persist a `FAILED` paraphrase job with a clear message such as:

```text
API paraphrase provider is disabled; use local or mock provider.
```
