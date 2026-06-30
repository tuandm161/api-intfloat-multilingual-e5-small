# Phase 01 - Config And Dependencies

## Dependency Changes

Add runtime dependencies:

```text
--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
llama-cpp-python>=0.3,<0.4
huggingface-hub>=0.26,<1.0
```

Notes:

- `huggingface-hub` may already be installed through `sentence-transformers`, but list it explicitly because local Qwen download depends on it.
- `llama-cpp-python` is the runtime for GGUF inference.
- On Windows, prefer the CPU wheel extra index above. Plain PyPI may try to build from source and fail if Visual Studio Build Tools or `nmake` is missing.
- If Windows installation still fails, document the fallback path using a local server later; do not change the default implementation away from GGUF in-app.

## Settings Additions

Add these fields to `Settings` in `app/core/config.py`:

```python
paraphrase_provider: GenerationProvider = GenerationProvider.local
local_paraphrase_model_repo_id: str = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
local_paraphrase_model_filename: str = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
local_paraphrase_context_tokens: int = 2048
local_paraphrase_max_tokens: int = 1024
local_paraphrase_temperature: float = 0.2
local_paraphrase_top_p: float = 0.9
local_paraphrase_repeat_penalty: float = 1.05
local_paraphrase_threads: int = 0
local_paraphrase_gpu_layers: int = 0
```

Validation constraints:

- Context tokens: `ge=512`, `le=8192`
- Max tokens: `ge=64`, `le=2048`
- Temperature: `ge=0`, `le=2`
- Top-p: `gt=0`, `le=1`
- Repeat penalty: `ge=1`, `le=2`
- Threads: `ge=0`
- GPU layers: `ge=0`

## Environment Defaults

Update `.env.example` with:

```env
PARAPHRASE_PROVIDER=local
LOCAL_PARAPHRASE_MODEL_REPO_ID=Qwen/Qwen2.5-1.5B-Instruct-GGUF
LOCAL_PARAPHRASE_MODEL_FILENAME=qwen2.5-1.5b-instruct-q4_k_m.gguf
LOCAL_PARAPHRASE_CONTEXT_TOKENS=2048
LOCAL_PARAPHRASE_MAX_TOKENS=1024
LOCAL_PARAPHRASE_TEMPERATURE=0.2
LOCAL_PARAPHRASE_TOP_P=0.9
LOCAL_PARAPHRASE_REPEAT_PENALTY=1.05
LOCAL_PARAPHRASE_THREADS=0
LOCAL_PARAPHRASE_GPU_LAYERS=0

GENERATION_PROVIDER=mock
```

Meaning:

- `PARAPHRASE_PROVIDER` controls paraphrase generation only.
- `GENERATION_PROVIDER` remains for document question generation.
- Default document generation stays `mock` to avoid accidentally routing document chunks to Qwen.

## Public Config

Extend `public_config()` to include:

```python
"paraphraseProvider": self.paraphrase_provider.value
```

Do not expose:

- Local filesystem cache paths.
- Any API key values.
- Full model download internals.
