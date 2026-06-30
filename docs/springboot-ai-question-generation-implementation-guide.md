# Hướng Dẫn Implement AI Question Generation Trong Spring Boot

> Mục tiêu: viết lại toàn bộ hướng triển khai từ demo FastAPI sang dự án Spring Boot chính, ở mức kiến trúc, entity, API contract và workflow.  
> Không chứa Java code cụ thể.  
> Ngày cập nhật: 30/06/2026.

---

## 1. Quyết Định Tổng Quan

Dự án Spring Boot sẽ giữ vai trò backend chính và nhúng luôn pipeline AI ở MVP để giảm độ phức tạp deploy.

- Quản lý tài liệu.
- Quản lý job tạo câu hỏi.
- Lưu PostgreSQL.
- Quản lý duyệt/sửa/từ chối/lưu câu hỏi.
- Quản lý audit, phân quyền, trạng thái.
- Extract, clean, section tree và chunking tài liệu.
- Gọi DeepSeek API cho tạo câu hỏi từ tài liệu.
- Chạy hoặc gọi lớp dedup/paraphrase theo cấu hình.

Quyết định MVP:

- Không tách Python AI Service ở giai đoạn đầu.
- Không deploy thêm một service AI riêng.
- Spring Boot gọi DeepSeek trực tiếp qua `DeepSeekClient`.
- Spring Boot tự quản lý document job, retry chunk, validation và review.
- E5/VietQuill local là phần cần cân nhắc kỹ khi nhúng vào JVM; có thể triển khai bằng ONNX Runtime Java/DJL hoặc để phase nâng cấp.

Nguyên tắc quan trọng: dù nhúng trong Spring Boot, vẫn phải tách module rõ ràng. Controller không gọi thẳng DeepSeek, E5 hoặc VietQuill.

AI Service riêng chỉ là hướng nâng cấp sau khi:

- Job tài liệu nặng hơn.
- Cần OCR/layout analysis mạnh.
- Cần chạy nhiều model local.
- Cần scale worker riêng.
- Deploy đã đủ ổn định để quản lý thêm service.

---

## 1.1. Quy Ước Ngôn Ngữ Toàn Ứng Dụng

Ứng dụng phải dùng tiếng Việt cho toàn bộ trải nghiệm người dùng.

Bắt buộc dùng tiếng Việt cho:

- Tên màn hình.
- Menu.
- Nút bấm.
- Badge trạng thái.
- Cảnh báo.
- Thông báo lỗi.
- Toast/alert.
- Nhãn form.
- Placeholder.
- Nội dung review.
- Hướng dẫn thao tác.
- Log/audit hiển thị cho người dùng.

Được giữ tiếng Anh cho:

- Tên model: `deepseek-v4-flash`, `intfloat/multilingual-e5-small`.
- Enum nội bộ trong database/API: `READY`, `GENERATED`, `NEED_REVIEW`.
- Field JSON/API: `documentId`, `questionPerChunk`, `sourceExcerpt`.
- Thuật ngữ chuyên môn xuất hiện trong câu hỏi gốc: `ABC`, `SpO2`, `Airway`, `Breathing`, `Circulation`, `mmHg`.

Backend nên có lớp mapping enum sang tiếng Việt để UI không hiển thị enum thô.

Ví dụ:

| Enum nội bộ | Nhãn tiếng Việt |
|---|---|
| `READY` | Sẵn sàng |
| `OCR_REQUIRED` | Cần OCR |
| `GENERATING` | Đang tạo |
| `PARTIALLY_COMPLETED` | Hoàn thành một phần |
| `FAILED` | Thất bại |
| `GOOD` | Đạt |
| `NEED_REVIEW` | Cần xem xét |
| `REJECTED` | Đã từ chối |
| `APPROVED` | Đã duyệt |
| `SAVED` | Đã lưu |

Prompt gửi DeepSeek cũng phải yêu cầu output tiếng Việt, trừ thuật ngữ tiếng Anh chuyên môn cần giữ nguyên.

---

## 2. Ba Thành Phần AI Cần Dùng

Trong tài liệu này, “2 model và API” được hiểu như sau:

### Model 1: `intfloat/multilingual-e5-small`

Vai trò:

- Chạy local.
- Tạo embedding cho câu hỏi.
- Kiểm tra trùng ngữ nghĩa.
- Không dùng để paraphrase.
- Không dùng để sinh câu hỏi.

Khi dùng E5, input nên có prefix đúng:

- Query/câu hỏi: `query: ...`
- Passage/câu trong bank: `passage: ...`

Trong hệ thống hiện tại, E5 là lớp validation/dedup, không phải lớp generation.

### Model 2: `ngwgsang/vietquill-vit5-base-tsubaki`

Vai trò:

- Chạy local.
- Dùng cho paraphrase câu hỏi và 4 đáp án.
- Phù hợp hơn Qwen 1.5B cho paraphrase tiếng Việt nhẹ trên laptop.
- Không dùng để tạo bộ câu hỏi từ tài liệu.

Luồng paraphrase phải giữ rõ:

- Stem/câu hỏi.
- Option A/B/C/D.
- Đáp án đúng.
- Giải thích.
- Protected terms như `ABC`, `SpO2`, `mmHg`, số liệu, đơn vị.

### API: DeepSeek

Vai trò:

- Dùng cho tạo câu hỏi từ tài liệu.
- Model chính: `deepseek-v4-flash`.
- Model fallback tùy chọn: `deepseek-v4-pro`.

Theo docs chính thức DeepSeek, API dùng base URL `https://api.deepseek.com`, hỗ trợ OpenAI-compatible `/chat/completions`, endpoint `/models`, và model ID hiện tại gồm `deepseek-v4-flash`, `deepseek-v4-pro`. Trước khi deploy production vẫn nên gọi `/models` hoặc kiểm tra docs vì model/pricing có thể thay đổi.

Nguồn tham khảo:

- DeepSeek Quick Start: https://api-docs.deepseek.com/
- Chat Completion API: https://api-docs.deepseek.com/api/create-chat-completion
- List Models API: https://api-docs.deepseek.com/api/list-models
- Models & Pricing: https://api-docs.deepseek.com/quick_start/pricing

---

## 3. Kiến Trúc Đề Xuất Cho MVP Nhúng Trong Spring Boot

```text
Spring Boot App / Monolith
  ├─ Document Module
  │   ├─ Upload
  │   ├─ Extract PDF/DOCX/TXT/MD
  │   ├─ Clean text
  │   ├─ Section detection
  │   └─ Chunking
  ├─ Generation Module
  │   ├─ DeepSeekClient
  │   ├─ KnowledgePointExtractor
  │   ├─ QuestionCandidateGenerator
  │   └─ QuestionValidator
  ├─ Dedup Module
  │   ├─ LexicalDuplicateChecker
  │   └─ EmbeddingDuplicateChecker sau này
  ├─ Paraphrase Module
  │   └─ VietQuill adapter sau này nếu nhúng local model
  ├─ Review Module
  ├─ Question Bank Module
  ├─ Audit Module
  ├─ PostgreSQL
  └─ External DeepSeek API
```

Module/service nên có:

- `DocumentIngestionService`
- `DocumentExtractor`
- `DocumentPreprocessor`
- `DocumentChunkingService`
- `DocumentQuestionJobService`
- `DeepSeekClient`
- `KnowledgePointExtractionService`
- `QuestionCandidateGenerationService`
- `QuestionCandidateValidationService`
- `DuplicateCheckService`
- `CandidateReviewService`
- `QuestionPublishService`
- `AuditService`

Controller chỉ nhận request và gọi service nghiệp vụ. Không để controller chứa prompt, retry logic, HTTP call DeepSeek hoặc validation rule.

---

## 4. Pipeline Tạo Câu Hỏi Từ Tài Liệu

Luồng MVP nên là:

```text
Upload document
→ Extract text
→ Clean text
→ Build section tree
→ Split hierarchical chunks
→ Extract knowledge points bằng DeepSeek Flash
→ Generate MCQ candidates bằng DeepSeek Flash
→ Deterministic validation
→ LLM validation bằng DeepSeek Flash
→ E5 semantic dedup
→ Persist candidate ở trạng thái chờ duyệt
→ Human review
→ Save approved question vào bank
```

Không gửi toàn bộ PDF 200-300 trang vào một request DeepSeek.

Mỗi chunk phải xử lý riêng để:

- Có evidence rõ.
- Retry được chunk lỗi.
- Không chạy lại toàn bộ job.
- Kiểm soát token/cost.

---

## 5. Entity PostgreSQL Đề Xuất

### `documents`

Lưu metadata tài liệu.

Field chính:

- `id`
- `filename`
- `content_type`
- `status`: `READY`, `OCR_REQUIRED`, `FAILED`
- `page_count`
- `chunk_count`
- `error_message`
- `created_by`
- `created_at`
- `updated_at`

Ghi chú:

- PDF scan/chưa đọc được text phải là `OCR_REQUIRED`.
- Không sinh câu hỏi từ tài liệu `OCR_REQUIRED`.

### `document_sections`

Lưu cây section rule-based.

Field chính:

- `id`
- `document_id`
- `parent_id`
- `title`
- `level`
- `order_index`
- `page_start`
- `page_end`
- `path`
- `confidence`

Ví dụ `path`:

```text
Chương 1 Cấp cứu ban đầu > 1.1 Theo dõi hô hấp
```

### `document_chunks`

Lưu chunk dùng cho generation.

Field chính:

- `id`
- `document_id`
- `section_id`
- `parent_chunk_id`
- `chunk_index`
- `chunk_type`: `generation`, sau này có thể thêm `retrieval`
- `page_start`
- `page_end`
- `section_title`
- `section_path`
- `text`
- `text_hash`
- `char_count`
- `token_count`
- `quality_flags`
- `previous_chunk_id`
- `next_chunk_id`

Ghi chú:

- `text_hash` dùng cho idempotency.
- `quality_flags` có thể gồm `LOW_INFORMATION_DENSITY`, `LOW_SECTION_CONFIDENCE`, `ABOVE_TARGET_TOKEN_RANGE`.

### `document_question_jobs`

Lưu phiên tạo câu hỏi.

Field chính:

- `id`
- `document_id`
- `provider`: `api`, `mock`, sau này có thể `local`
- `model`
- `prompt_version`
- `status`: `CREATED`, `GENERATING`, `GENERATED`, `PARTIALLY_COMPLETED`, `FAILED`
- `questions_per_chunk`
- `chunk_count`
- `completed_chunk_count`
- `failed_chunk_count`
- `candidate_count`
- `chunk_errors`
- `llm_call_count`
- `total_prompt_tokens`
- `total_completion_tokens`
- `total_tokens`
- `total_latency_ms`
- `estimated_cost_usd`
- `error_message`

### `document_knowledge_points`

Lưu knowledge point DeepSeek trích từ chunk.

Field chính:

- `id`
- `job_id`
- `document_id`
- `chunk_id`
- `source_key`: ví dụ `KP1`
- `statement`
- `knowledge_type`: `definition`, `principle`, `procedure`, `warning`, `fact`
- `importance`: `low`, `medium`, `high`
- `source_excerpt`
- `generation_eligible`
- `raw_json`

Ghi chú:

- Không bắt buộc chunk nào cũng có knowledge point.
- Nếu 0 knowledge point thì không sinh câu hỏi cho chunk đó.

### `document_question_candidates`

Lưu câu hỏi AI đề xuất.

Field chính:

- `id`
- `job_id`
- `document_id`
- `chunk_id`
- `stem`
- `option_a`
- `option_b`
- `option_c`
- `option_d`
- `correct_answer`
- `explanation`
- `topic`
- `difficulty`
- `source_excerpt`
- `generation_key`
- `raw_json`
- `quality_score`
- `llm_validation`
- `label`: `GOOD`, `NEED_REVIEW`, `REJECTED`
- `warnings`
- `status`: `GENERATED`, `VALIDATED`, `NEED_REVIEW`, `APPROVED`, `REJECTED`, `SAVED`
- `duplicate_max_similarity`
- `duplicate_question_id`
- `duplicate_question_stem_snapshot`
- `reviewer_notes`
- `saved_question_id`

### `questions`

Bảng câu hỏi chính của hệ thống.

Khi candidate được approve và save:

- Tạo record mới trong `questions`.
- Gắn `source_document`.
- Tạo embedding E5.
- Cập nhật vector index hoặc bảng embedding.

---

## 6. API Nội Bộ Trong Spring Boot

### Document API

#### Upload tài liệu

```text
POST /api/documents
```

Input:

- Multipart file.

Output:

- `documentId`
- `status`
- `pageCount`
- `chunkCount`
- `sections`
- `chunks`

### Question Generation Job API

#### Tạo job sinh câu hỏi

```text
POST /api/documents/{documentId}/question-jobs
```

Body:

```json
{
  "questionsPerChunk": 3
}
```

Output:

- `jobId`
- `status`
- `candidateCount`
- `chunkErrors`
- `knowledgePoints`
- `candidates`

#### Xem job detail

```text
GET /api/document-question-jobs/{jobId}
```

Trả về:

- Metadata job.
- Usage token/cost.
- Knowledge points.
- Candidates.
- Cảnh báo.
- Duplicate info.

#### Retry chunk lỗi

```text
POST /api/document-question-jobs/{jobId}/retry-failed-chunks
```

Chỉ retry chunk đang lỗi. Không chạy lại chunk thành công.

### Candidate Review API

#### Xem candidate

```text
GET /api/document-question-candidates/{candidateId}
```

#### Sửa candidate

```text
PUT /api/document-question-candidates/{candidateId}
```

Body gồm:

- `stem`
- `optionA`
- `optionB`
- `optionC`
- `optionD`
- `correctAnswer`
- `explanation`
- `difficulty`
- `topic`
- `sourceExcerpt`

Sau khi sửa, phải revalidate deterministic + E5.

#### Approve

```text
POST /api/document-question-candidates/{candidateId}/approve
```

#### Reject

```text
POST /api/document-question-candidates/{candidateId}/reject
```

#### Save vào question bank

```text
POST /api/document-question-candidates/{candidateId}/save-as-question
```

Chỉ cho save nếu candidate đã `APPROVED`.

---

## 7. Ranh Giới Module AI Nội Bộ Trong Spring Boot

MVP không có AI Service riêng. Các “API” dưới đây nên hiểu là interface/service contract nội bộ trong Spring Boot, không phải endpoint HTTP bắt buộc.

### Extract + Chunk

Input:

- File hoặc file storage key.
- Document metadata.

Output:

- Pages.
- Sections.
- Chunks.
- Trạng thái: `READY` hoặc `OCR_REQUIRED`.

### Generate Questions For Chunk

Input:

```json
{
  "documentId": "...",
  "jobId": "...",
  "chunkId": "...",
  "chunkText": "...",
  "sectionPath": "...",
  "questionsPerChunk": 3,
  "targetLanguage": "vi"
}
```

Output:

```json
{
  "provider": "api",
  "model": "deepseek-v4-flash",
  "promptVersion": "docgen-mvp-flash-v1",
  "usage": {
    "promptTokens": 0,
    "completionTokens": 0,
    "totalTokens": 0,
    "latencyMs": 0,
    "callCount": 0
  },
  "knowledgePoints": [],
  "questions": []
}
```

### Validate Candidate

Output:

```json
{
  "answerable": true,
  "singleBestAnswer": true,
  "correctAnswerSupported": true,
  "qualityScore": 0.86,
  "issues": [],
  "rationale": "..."
}
```

### Embedding/Dedup

Input:

- Nội dung câu hỏi ứng viên.
- Phạm vi câu hỏi có sẵn cần so trùng.

Output:

- `maxSimilarity`
- `matchedQuestionId`
- `decision`: `PASS`, `NEED_REVIEW`, `REJECT`

### Paraphrase

Input:

- Câu hỏi đầy đủ với 4 đáp án.
- Đáp án đúng.
- Số lượng cần tạo.

Output:

- Paraphrased stem.
- Paraphrased options.
- Validation warnings.

Nếu sau này tách Python AI Service, các contract nội bộ này có thể chuyển thành HTTP endpoint mà không đổi luồng nghiệp vụ chính.

---

## 8. DeepSeek Prompt Strategy

Không gọi DeepSeek một bước “đọc chunk rồi tạo ngay nhiều câu”.

Nên gọi theo 3 loại task:

### Task 1: Knowledge extraction

Input:

- Chunk text.
- Section path.

Output:

- `knowledgePoints`.

Mỗi knowledge point gồm:

- `id`
- `statement`
- `type`
- `importance`
- `sourceExcerpt`

### Task 2: Question generation

Input:

- Chunk text.
- Knowledge points.
- Output schema.
- Số câu cần tạo.

Output:

- `questions`.

Mỗi câu gồm:

- `stem`
- `optionA`
- `optionB`
- `optionC`
- `optionD`
- `correctAnswer`
- `explanation`
- `difficulty`
- `topic`
- `sourceExcerpt`
- `knowledgePointId`

### Task 3: Question validation

Input:

- Chunk text.
- Candidate question.

Output:

- `answerable`
- `singleBestAnswer`
- `correctAnswerSupported`
- `qualityScore`
- `issues`
- `rationale`

---

## 9. Validation Rules

### Deterministic validation

Reject nếu:

- Thiếu stem.
- Thiếu option A/B/C/D.
- `correctAnswer` không thuộc A/B/C/D.
- Option bị trùng.
- Option chứa mẫu không phù hợp:
  - “Tất cả đều đúng”
  - “Cả A và B”
  - “Không có đáp án nào”
- Candidate trùng chính xác với câu có sẵn.

Need review nếu:

- Trích dẫn nguồn không tìm thấy rõ trong chunk.
- Vector index chưa sẵn sàng.
- Similarity với câu cũ ở vùng nghi ngờ.

### LLM validation

Reject nếu:

- `answerable = false`
- `singleBestAnswer = false`
- `correctAnswerSupported = false`
- `qualityScore < threshold`

Ngưỡng ban đầu:

- Reject quality dưới `0.55`.
- Need review nếu có warning nhưng không fatal.

### E5 dedup

Khuyến nghị ngưỡng ban đầu:

- `>= 0.93`: reject hoặc strong duplicate.
- `0.80 - 0.93`: need review.
- `< 0.80`: pass.

Các ngưỡng này phải hiệu chỉnh lại bằng dữ liệu thật của bệnh viện.

---

## 10. Idempotency Và Retry

Mỗi chunk generation cần `generationKey` dựa trên:

- Provider.
- Model.
- Prompt version.
- Số câu hỏi mỗi chunk.
- Chunk text hash.
- Target language.

Nếu cùng key đã có candidate thành công:

- Không gọi lại DeepSeek.
- Clone hoặc reuse kết quả cũ tùy nghiệp vụ.

Retry:

- Retry network/timeout/rate limit theo cấu hình.
- Không retry vô hạn.
- Một chunk lỗi không làm fail toàn job.
- Job có thể `PARTIALLY_COMPLETED`.

---

## 11. Review Workflow

Candidate AI không được tự động publish.

Luồng:

```text
GENERATED
→ VALIDATED / NEED_REVIEW / REJECTED
→ APPROVED hoặc REJECTED bởi reviewer
→ SAVED vào question bank
```

Reviewer cần thấy:

- Stem.
- 4 đáp án.
- Đáp án đúng.
- Giải thích.
- Trích dẫn nguồn.
- Page range.
- Section path.
- Knowledge point.
- Duplicate warning.
- LLM validation rationale.
- Quality score.

---

## 12. Configuration Spring Boot

Các cấu hình nên có:

```text
ai.generation.provider=api
ai.generation.api-base-url=https://api.deepseek.com
ai.generation.model=deepseek-v4-flash
ai.generation.fallback-model=deepseek-v4-pro
ai.generation.timeout-seconds=60
ai.generation.max-retries=1

ai.embedding.provider=e5
ai.embedding.model=intfloat/multilingual-e5-small
ai.embedding.dimension=384

ai.paraphrase.provider=local
ai.paraphrase.model=ngwgsang/vietquill-vit5-base-tsubaki

document.chunk.target-tokens=750
document.chunk.max-tokens=1200
document.questions-per-chunk=3

validation.duplicate.strong-min=0.93
validation.duplicate.review-min=0.80
validation.quality.reject-min=0.55
```

API key phải đặt trong secret manager hoặc biến môi trường:

```text
DEEPSEEK_API_KEY=...
```

Không commit API key vào repo.

---

## 13. UI Cần Có

Toàn bộ UI phải là tiếng Việt. Không hiển thị trực tiếp enum kỹ thuật cho người dùng.

### Trang tài liệu

Hiển thị:

- Tên file.
- Trạng thái.
- Số trang.
- Số chunk.
- Cấu trúc tài liệu.
- Xem trước chunk.
- Nút tạo câu hỏi.

### Trang job

Hiển thị:

- Trạng thái phiên tạo.
- Model.
- Prompt version.
- Tokens.
- Thời gian xử lý.
- Ước tính chi phí.
- Chunk lỗi.
- Retry chunk lỗi.
- Knowledge points.
- Danh sách câu hỏi đề xuất.

### Candidate card

Hiển thị:

- Nhãn: Đạt, Cần xem xét, Đã từ chối.
- Trạng thái.
- Trang/section nguồn.
- Câu hỏi/các đáp án.
- Đáp án đúng.
- Giải thích.
- Trích dẫn nguồn.
- Điểm chất lượng AI.
- Nhận xét AI.
- Thông tin trùng lặp.
- Danh sách cảnh báo.
- Nút: Lưu chỉnh sửa, Duyệt, Từ chối, Lưu vào ngân hàng câu hỏi.

---

## 14. Những Gì Chưa Nên Làm Ngay

Chưa nên:

- Dùng VietQuill/BARTpho để tạo câu hỏi từ tài liệu.
- Dùng E5 để sinh câu hỏi.
- Gửi toàn bộ tài liệu vào DeepSeek một lần.
- Tạo quá nhiều question type trước khi single-choice ổn.
- Tự publish câu hỏi AI.
- OCR production-grade nếu tài liệu demo là PDF text/DOCX.
- Benchmark local LLM document generation nếu chưa có golden dataset.

---

## 15. Definition Of Done Cho Spring Boot MVP

MVP có thể coi là ổn khi:

- Upload được PDF text, DOCX, TXT/MD.
- PDF không có text được đánh dấu `OCR_REQUIRED`.
- Có section tree và chunk metadata.
- Tạo job sinh câu hỏi bằng DeepSeek Flash.
- Có knowledge point được lưu.
- Có candidate MCQ đầy đủ 4 đáp án.
- Có evidence/source excerpt.
- Có deterministic validation.
- Có LLM validation.
- Có E5 dedup.
- Có partial completion và retry chunk lỗi.
- Reviewer duyệt/sửa/từ chối/lưu được.
- Lưu model, prompt version, tokens, latency, estimated cost.
- Không log API key.
- Có test bằng mock DeepSeek, không gọi API thật trong CI.

---

## 16. Điểm Cần Chốt Khi Thảo Luận

Cần chốt thêm trước khi implement Spring Boot:

1. File gốc lưu ở đâu: database, local disk, MinIO/S3, hay storage nội bộ bệnh viện?
2. PostgreSQL schema dùng bảng option/evidence riêng hay giữ option A-D trong candidate?
3. Review flow có cần phân quyền reviewer/admin ngay không?
4. Khi candidate bị edit, có gọi lại LLM validation không hay chỉ deterministic + E5?
5. Có cần bật DeepSeek Pro fallback không, hay MVP chỉ dùng Flash để kiểm soát chi phí?
6. E5 local trong Spring Boot dùng ONNX Runtime Java, DJL, hay tạm dùng lexical dedup trước?
7. VietQuill local có nhúng vào Spring Boot ngay không, hay paraphrase để phase sau?
8. Có tài liệu mẫu/golden dataset để hiệu chỉnh ngưỡng E5 không?
9. Toàn bộ nhãn/warning/error tiếng Việt sẽ quản lý bằng message bundle hay enum mapper trong code?
