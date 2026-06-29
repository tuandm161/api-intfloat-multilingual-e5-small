# Phase 00 - Overview

## Goal

Implement local paraphrase generation for the question bank app using Qwen2.5-1.5B-Instruct, without calling the external DeepSeek paraphrase API.

The target workflow is:

```text
Qwen local generates paraphrase candidates
-> E5 validates semantic similarity and duplicate risk
-> rule checks flag risky output
-> reviewer approves or rejects
```

## Runtime Decision

- Use GGUF in-app runtime with `llama-cpp-python`.
- Load model lazily on the first local paraphrase request.
- Do not load Qwen during FastAPI startup.
- Keep model state cached in-process after first load.

## Model

- Repository: `Qwen/Qwen2.5-1.5B-Instruct-GGUF`
- File: `qwen2.5-1.5b-instruct-q4_k_m.gguf`
- Expected local cache behavior: download once from Hugging Face, then reuse from cache.
- Target machine: personal laptop with 8-16 GB RAM.

## Scope

In scope:

- Replace the current `LocalParaphraseGenerator` stub with a real local Qwen generator.
- Add local paraphrase configuration.
- Make the paraphrase UI/API use the local provider by default.
- Keep E5-small as the validation and duplicate-detection layer.
- Keep mock provider for tests and quick demos.

Out of scope:

- Do not use Qwen for document question generation in this phase.
- Do not change the database schema.
- Do not remove DeepSeek document-generation code.
- Do not download Qwen during tests.

## Success Criteria

- Creating a paraphrase job with `provider=local` produces candidate stems from Qwen.
- Generated candidates preserve medical meaning and protected terms such as `ABC`, `ICU`, `SpO2`, `mmHg`, and `NANDA`.
- Validation still uses E5 and existing rule checks.
- Tests do not require Qwen to be installed or downloaded.
