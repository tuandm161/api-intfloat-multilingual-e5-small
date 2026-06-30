# ĐẶC TẢ TRIỂN KHAI HỆ THỐNG TẠO BỘ CÂU HỎI TỪ TÀI LIỆU

> Tài liệu bàn giao cho coding agent  
> Phiên bản: 1.1  
> Ngày chốt: 30/06/2026  
> Trạng thái: Đặc tả thiết kế đã căn chỉnh cho MVP dùng DeepSeek Flash

---

## 1. Mục đích tài liệu

Tài liệu này mô tả đầy đủ hướng triển khai tính năng tạo bộ câu hỏi tiếng Việt từ tài liệu dài, chủ yếu là PDF/DOCX khoảng 200–300 trang, phục vụ hệ thống CareHub/VietDuc-Care.

**Quyết định MVP hiện tại:** phần tạo câu hỏi từ tài liệu dùng DeepSeek API, model chính là `deepseek-v4-flash`. Các provider local cho document question generation chỉ giữ ở mức abstraction/benchmark sau, không phải đường chạy chính của MVP.

Coding agent phải đọc toàn bộ tài liệu trước khi triển khai. Không được bắt đầu bằng cách gửi nguyên PDF hoặc toàn bộ nội dung tài liệu vào LLM. Hệ thống phải xử lý tài liệu theo pipeline có cấu trúc, lưu được nguồn dẫn chứng của từng câu hỏi, dùng DeepSeek Flash cho MVP, đồng thời giữ nguyên các thành phần AI hiện có như E5 dùng để kiểm tra trùng.

Tài liệu này chỉ mô tả:

- Kiến trúc.
- Luồng xử lý.
- Quy tắc tiền xử lý.
- Quy tắc chunking.
- Chiến lược gọi LLM.
- Chuẩn dữ liệu.
- Validation.
- Kiểm tra trùng.
- Bảo mật.
- Logging, chi phí và retry.
- Phân chia phase triển khai.
- Tiêu chí nghiệm thu.

Tài liệu này không cung cấp source code.

---

## 2. Bối cảnh và yêu cầu chính

### 2.1. Bối cảnh

Hệ thống cần nhận tài liệu tiếng Việt, phần lớn thuộc lĩnh vực bệnh viện, điều dưỡng, đào tạo, kiểm soát nhiễm khuẩn, quy trình kỹ thuật hoặc tài liệu chuyên môn. Một tài liệu có thể dài 200–300 trang và chứa:

- Chương, mục, tiểu mục.
- Đoạn lý thuyết.
- Định nghĩa.
- Danh sách đánh số.
- Quy trình nhiều bước.
- Checklist.
- Bảng.
- Hình ảnh hoặc sơ đồ.
- Chú ý, cảnh báo, chống chỉ định, tai biến và cách xử trí.
- Header, footer, số trang và nội dung lặp.
- Trang scan không có text layer.

### 2.2. Mục tiêu nghiệp vụ

Từ một tài liệu, hệ thống phải có khả năng:

1. Phân tích và trích xuất nội dung có cấu trúc.
2. Làm sạch nội dung mà không làm mất ý nghĩa chuyên môn.
3. Tách tài liệu thành các đơn vị kiến thức hợp lý.
4. Trích xuất knowledge point từ từng đơn vị kiến thức.
5. Tạo câu hỏi tiếng Việt theo loại và độ khó được yêu cầu.
6. Tạo đáp án, phương án lựa chọn, giải thích và evidence.
7. Kiểm tra câu hỏi có trả lời được từ tài liệu hay không.
8. Kiểm tra câu hỏi có đúng một đáp án tốt nhất hay không.
9. Dùng `intfloat/multilingual-e5-small` để kiểm tra trùng ngữ nghĩa.
10. Lưu chính xác tài liệu, trang, section và đoạn nguồn của từng câu hỏi.
11. Đưa câu hỏi vào trạng thái chờ người dùng duyệt trước khi sử dụng chính thức.
12. Hỗ trợ DeepSeek API cloud ở MVP và thiết kế interface để sau này có thể thêm model local mà không thay đổi nghiệp vụ cốt lõi.

### 2.3. Yêu cầu phi chức năng

- Ngôn ngữ đầu ra mặc định: tiếng Việt.
- Không phụ thuộc cứng vào một nhà cung cấp LLM.
- Có thể retry theo từng chunk, không phải chạy lại toàn bộ tài liệu.
- Có idempotency để tránh sinh trùng khi job bị gọi lại.
- Có giới hạn chi phí và số token.
- Có log nhưng không ghi API key hoặc toàn bộ dữ liệu nhạy cảm.
- Có thể theo dõi tiến độ xử lý tài liệu.
- Có thể tạm dừng, hủy hoặc chạy lại phần lỗi.
- Kết quả AI không được tự động coi là dữ liệu chính thức nếu chưa được duyệt.

---

## 3. Phạm vi phiên bản đầu tiên

### 3.1. Trong phạm vi

Phiên bản đầu tiên cần hỗ trợ ở mức MVP:

- PDF có text layer.
- DOCX.
- TXT/MD nếu hệ thống hiện tại đã hỗ trợ.
- Tiếng Việt và tài liệu có xen một phần tiếng Anh.
- Câu hỏi một đáp án.
- Mức độ dễ và trung bình; mức khó chỉ tạo nếu Flash cho kết quả đạt validation.
- Sinh đáp án và giải thích.
- Evidence bắt buộc.
- DeepSeek API làm provider mặc định, ưu tiên `deepseek-v4-flash`.
- E5-small local để semantic deduplication.
- Duyệt thủ công trước khi publish.

### 3.2. Ngoài phạm vi phiên bản đầu tiên

Chưa bắt buộc ở phiên bản đầu:

- PDF scan và OCR production-grade.
- PDF hỗn hợp hoặc layout-heavy có nhiều bảng/cột phức tạp.
- Câu hỏi đúng/sai.
- Câu hỏi tự luận ngắn.
- Provider local để tạo câu hỏi từ tài liệu.
- Tự động hiểu chính xác mọi sơ đồ y khoa phức tạp.
- Tự động tạo câu hỏi trực tiếp từ video hoặc audio.
- Câu hỏi kéo-thả giao diện phức tạp.
- Chấm bài tự luận dài bằng AI.
- Fine-tune LLM.
- Tự động publish câu hỏi không qua kiểm duyệt.
- Tạo câu hỏi “rất khó” từ toàn bộ tài liệu trong một lượt.
- Đảm bảo tuyệt đối model local có chất lượng ngang cloud.

---

## 4. Quyết định kiến trúc đã chốt

### 4.1. Kiến trúc tổng thể

Luồng hệ thống phải được thiết kế như sau:

```text
Người dùng tải tài liệu
        ↓
Spring Boot tạo document/job và lưu metadata
        ↓
AI Service nhận yêu cầu xử lý
        ↓
Parse/OCR/layout analysis tại hệ thống của mình
        ↓
Tiền xử lý và xây dựng section tree
        ↓
Structure-aware hierarchical chunking
        ↓
LLM trích xuất knowledge point
        ↓
LLM tạo câu hỏi ứng viên
        ↓
Rule validation + LLM validation
        ↓
E5-small kiểm tra trùng
        ↓
Lưu câu hỏi ở trạng thái chờ duyệt
        ↓
Người có quyền review, sửa, duyệt hoặc từ chối
```

### 4.2. Vai trò của từng thành phần

#### Spring Boot

Chịu trách nhiệm nghiệp vụ chính:

- Quản lý người dùng và phân quyền.
- Quản lý tài liệu.
- Tạo và theo dõi generation job.
- Quản lý bộ câu hỏi.
- Duyệt câu hỏi.
- Lưu dữ liệu nghiệp vụ trong PostgreSQL.
- Gọi AI Service thông qua API nội bộ.
- Không trực tiếp chứa logic OCR, chunking, embedding hoặc prompt orchestration.

#### Python AI Service

Chịu trách nhiệm pipeline AI:

- Nhận tài liệu hoặc đường dẫn file nội bộ.
- Parse PDF/DOCX.
- OCR.
- Nhận diện bố cục.
- Làm sạch nội dung.
- Tạo section tree.
- Chunking.
- Gọi LLM provider.
- Validate đầu ra.
- Chạy E5-small.
- Tính quality score.
- Trả và/hoặc ghi kết quả theo hợp đồng đã thống nhất.

Framework mục tiêu: FastAPI. Tuy nhiên logic nghiệp vụ phải tách khỏi framework để dễ test.

#### PostgreSQL

Lưu:

- Document metadata.
- Processing job.
- Section.
- Chunk.
- Knowledge point.
- Question candidate.
- Option.
- Evidence.
- Validation result.
- Duplicate result.
- Review action.
- LLM usage/cost metadata.

#### Object/file storage

Lưu:

- File gốc.
- Bản text đã extract.
- Ảnh trang cần OCR nếu có.
- Artifact trung gian cần audit.

Không lưu file lớn trực tiếp trong cột database nếu kiến trúc hiện tại đã có file storage riêng.

---

## 5. Chiến lược LLM: cloud và local

### 5.1. Nguyên tắc chung

Hệ thống phải có abstraction `LLM Provider`. Toàn bộ pipeline không được gọi trực tiếp DeepSeek ở nhiều nơi. Mọi lời gọi model phải đi qua một lớp provider chung.

Các provider ban đầu:

- DeepSeek cloud provider.
- Local OpenAI-compatible provider hoặc Ollama/provider khác cho model instruct sau benchmark.

MVP chỉ bắt buộc DeepSeek cloud provider hoạt động. Local provider cần được giữ như extension point hoặc mock đầy đủ; không coi local là blocker của MVP.

### 5.2. Provider mặc định: DeepSeek API cloud

Provider cloud là hướng chính cho bản demo và triển khai ban đầu vì:

- Chất lượng instruction following tốt hơn model local nhỏ.
- Khả năng sinh câu hỏi tình huống và phương án nhiễu tốt hơn.
- JSON output ổn định hơn.
- Không cần GPU server.
- Dễ mở rộng khi nhiều tài liệu được xử lý.

Model mặc định tại thời điểm chốt đặc tả:

- `deepseek-v4-flash`: tác vụ chính của MVP, gồm extraction có cấu trúc, tạo câu dễ/trung bình, format JSON và validation sơ bộ.
- `deepseek-v4-pro`: fallback tùy chọn cho phase sau, câu khó, multi-chunk reasoning hoặc validation phức tạp. MVP có thể tắt Pro hoàn toàn để kiểm soát chi phí và độ phức tạp.

Model name phải nằm trong configuration, không hard-code trong business logic. Trước khi deploy, hệ thống nên kiểm tra model còn khả dụng thông qua endpoint danh sách model hoặc cấu hình môi trường.

### 5.3. Provider thay thế: model local

Model local mục tiêu sau MVP:

- `Qwen/Qwen3-4B` hoặc một bản instruct/quantized tương thích đã được benchmark nội bộ.

Lý do chọn làm candidate:

- Kích thước phù hợp hơn với máy 32 GB RAM.
- Hỗ trợ đa ngôn ngữ.
- Có thể chạy qua server OpenAI-compatible hoặc Ollama/llama.cpp tùy môi trường.
- Có thể dùng khi tài liệu không được phép gửi lên cloud.

Model local không được mặc định coi là tương đương DeepSeek. Trước khi đưa vào dùng chính thức, phải benchmark bằng bộ câu hỏi tiếng Việt thực tế của dự án.

Không dùng VietQuill/BARTpho để tạo câu hỏi từ tài liệu trong MVP. Các model này phù hợp hơn cho paraphrase/seq2seq, không phải instruction-following MCQ generation.

### 5.4. Routing model

Quy tắc khởi đầu:

| Tác vụ | Model ưu tiên | Thinking |
|---|---|---|
| Trích knowledge point | Flash | Tắt |
| Sinh câu dễ | Flash | Tắt |
| Sinh câu trung bình | Flash | Tắt |
| Sinh câu khó trong MVP | Flash | Tắt, giới hạn nếu validation không đạt |
| Sinh câu dựa trên 2–3 chunk | Không làm trong MVP hoặc dùng Pro sau benchmark | Bật nếu dùng Pro |
| Kiểm tra JSON/format | Flash | Tắt |
| Kiểm tra answerability đơn giản | Flash | Tắt |
| Kiểm tra nhiều đáp án đúng | Flash trong MVP, Pro sau nếu cần | Tắt trong MVP |
| Chế độ offline/private | Local instruct model sau benchmark | Theo benchmark |

Routing phải cấu hình được. Không viết điều kiện model rải rác trong source code.

### 5.5. Quy tắc dữ liệu khi dùng cloud

Không gửi nguyên file PDF lên model chỉ để sinh câu hỏi.

Chỉ gửi:

- System instruction.
- Metadata section cần thiết.
- Chunk văn bản đã làm sạch.
- Knowledge point liên quan.
- Yêu cầu loại câu hỏi và độ khó.
- Output schema.

Trước khi gửi cloud, phải có bước phát hiện hoặc loại bỏ thông tin định danh không cần thiết, ví dụ:

- Tên người bệnh.
- Mã bệnh án.
- Số điện thoại.
- Email cá nhân.
- Địa chỉ chi tiết.
- Số định danh.
- Thông tin nhân sự không cần cho câu hỏi.

Nếu tài liệu được đánh dấu `confidential` hoặc `local_only`, pipeline không được sử dụng cloud provider.

---

## 6. Pipeline xử lý tài liệu

### 6.1. Các stage bắt buộc

Một generation job phải đi qua các stage rõ ràng:

1. Upload/registration.
2. File validation.
3. Document classification.
4. Content extraction.
5. OCR nếu cần.
6. Layout/element normalization.
7. Text cleanup.
8. Section tree construction.
9. Chunk generation.
10. Chunk quality check.
11. Knowledge point extraction.
12. Question generation.
13. Deterministic validation.
14. LLM validation.
15. Semantic deduplication.
16. Quality scoring.
17. Persist candidates.
18. Human review.
19. Approval/publication.

Mỗi stage phải có trạng thái riêng để có thể retry từ stage lỗi.

Đối với MVP dùng DeepSeek Flash, có thể triển khai stage rút gọn trước:

1. Upload/registration.
2. File validation.
3. Content extraction cho PDF text/DOCX/TXT/MD.
4. Text cleanup.
5. Heading/section detection ở mức rule-based.
6. Chunk generation.
7. Chunk quality check.
8. Knowledge point extraction bằng Flash.
9. Question generation bằng Flash.
10. Deterministic validation.
11. LLM validation bằng Flash nếu deterministic validation chưa đủ.
12. E5 semantic deduplication.
13. Persist candidates.
14. Human review.

OCR production-grade, layout analysis chi tiết, retry theo stage nhỏ và local document-generation provider thuộc phase hardening nếu cần triển khai nhanh.

### 6.2. Trạng thái job đề xuất

- `CREATED`
- `VALIDATING_FILE`
- `EXTRACTING`
- `OCR_PROCESSING`
- `PREPROCESSING`
- `CHUNKING`
- `EXTRACTING_KNOWLEDGE`
- `GENERATING_QUESTIONS`
- `VALIDATING_QUESTIONS`
- `DEDUPLICATING`
- `READY_FOR_REVIEW`
- `COMPLETED`
- `PARTIALLY_COMPLETED`
- `FAILED`
- `CANCELLED`

Cần lưu phần trăm tiến độ dựa trên stage và số chunk đã hoàn thành, không dựa vào thời gian ước lượng mơ hồ.

---

## 7. Phân loại và trích xuất tài liệu

### 7.1. Phân loại theo khả năng đọc text

Mỗi PDF phải được xác định là một trong các loại:

1. Text PDF: phần lớn trang có text layer hợp lệ.
2. Scan PDF: gần như toàn bộ trang là ảnh.
3. Mixed PDF: có trang có text, có trang cần OCR.
4. Layout-heavy PDF: nhiều bảng, nhiều cột, form hoặc sơ đồ.

Phân loại nên thực hiện theo từng trang khi cần, không chỉ theo toàn file.

### 7.2. Parser khuyến nghị

#### PDF đơn giản có text layer

Ưu tiên parser nhanh, ví dụ PyMuPDF hoặc cơ chế `fast` tương đương.

#### PDF có bảng hoặc bố cục phức tạp

Dùng layout-aware parser, ví dụ Unstructured `hi_res` hoặc Docling. Mục tiêu là giữ được element type và metadata trang, không chỉ text phẳng.

#### PDF scan

Dùng OCR với ngôn ngữ:

- Vietnamese.
- English.

Không OCR lại trang đã có text layer tốt vì có thể làm giảm chất lượng dấu tiếng Việt và tăng thời gian xử lý.

### 7.3. Output chuẩn sau extraction

Sau extraction, nội dung không được tồn tại chỉ dưới dạng một string dài. Mỗi element phải có tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| element_id | ID duy nhất |
| document_id | Tài liệu nguồn |
| page_number | Trang nguồn |
| order_index | Thứ tự trong tài liệu |
| element_type | title, heading, paragraph, list item, table, caption, note... |
| raw_text | Text gốc sau extract/OCR |
| normalized_text | Text sau làm sạch |
| bounding_box | Tọa độ nếu parser cung cấp |
| extraction_method | direct text, OCR, layout parser |
| confidence | Độ tin cậy nếu OCR/parser cung cấp |

Element type tối thiểu cần hỗ trợ:

- Title.
- Heading cấp 1–3.
- Paragraph.
- List item.
- Table.
- Table caption.
- Image caption.
- Note.
- Warning.
- Header.
- Footer.
- Page number.
- Reference.
- Unknown.

---

## 8. Tiền xử lý nội dung

### 8.1. Nguyên tắc

Tiền xử lý phải làm sạch nhiễu nhưng giữ nguyên ý nghĩa chuyên môn. Trong tài liệu y khoa, một từ phủ định hoặc một đơn vị đo có thể làm thay đổi hoàn toàn đáp án.

### 8.2. Các bước nên thực hiện

- Chuẩn hóa Unicode NFC.
- Chuẩn hóa khoảng trắng.
- Chuẩn hóa line break.
- Nối các dòng thuộc cùng một đoạn.
- Nối từ bị ngắt cuối dòng do layout hoặc OCR.
- Chuẩn hóa bullet và danh sách đánh số.
- Giữ nguyên thứ tự danh sách.
- Phát hiện và loại header/footer lặp.
- Loại số trang đứng riêng.
- Loại watermark lặp.
- Sửa một số lỗi OCR có độ tin cậy cao.
- Bảo toàn ký hiệu, liều lượng, đơn vị, tỷ lệ và khoảng thời gian.
- Bảo toàn mã mục, mã quy trình và số điều.
- Đánh dấu đoạn có chất lượng OCR thấp.
- Loại nội dung lặp chính xác do scan hoặc parser sinh đôi.

### 8.3. Không được thực hiện mặc định

- Không bỏ dấu tiếng Việt.
- Không lowercase toàn bộ dữ liệu nguồn.
- Không xóa toàn bộ dấu câu.
- Không loại stopword.
- Không stemming hoặc lemmatization mạnh.
- Không xóa các từ phủ định như “không”, “chưa”, “trừ”, “chống chỉ định”.
- Không tự sửa thuật ngữ chuyên môn chỉ dựa trên từ điển thông thường.
- Không tự chuyển đổi đơn vị.
- Không tóm tắt toàn bộ tài liệu trước khi chunk.

### 8.4. Phát hiện nội dung không dùng để sinh câu hỏi

Các phần sau có thể đặt `skip_generation = true`:

- Mục lục.
- Lời nói đầu không có kiến thức kiểm tra.
- Danh sách tác giả.
- Thông tin xuất bản.
- Header/footer.
- Trang trắng.
- Form trống.
- Chữ ký.
- Mã QR.
- Tài liệu tham khảo.
- Nội dung lặp.

Không được tự động bỏ:

- Cảnh báo.
- Chú ý.
- Chỉ định.
- Chống chỉ định.
- Ngoại lệ.
- Tai biến.
- Cách xử trí.
- Tiêu chí đánh giá.
- Điều kiện thực hiện.

---

## 9. Xây dựng cấu trúc tài liệu

### 9.1. Section tree

Sau preprocessing, phải xây dựng cây tài liệu:

```text
Document
└── Chapter
    └── Section
        └── Subsection
            └── Elements
```

Mỗi node cần lưu:

- ID.
- Tiêu đề.
- Cấp heading.
- Parent ID.
- Thứ tự.
- Trang bắt đầu/kết thúc.
- Danh sách element.
- Path đầy đủ từ document đến subsection.

### 9.2. Phát hiện heading

Heading có thể được xác định từ:

- Style trong DOCX.
- Font size/font weight trong PDF.
- Numbering pattern như `1.`, `1.1`, `I.`, `A.`.
- Khoảng trắng trước/sau.
- Element type do layout parser trả về.
- Quy tắc kết hợp thay vì chỉ regex.

Nếu không thể xác định cấu trúc tin cậy, hệ thống được phép tạo pseudo-section theo trang hoặc nhóm đoạn nhưng phải đánh dấu confidence thấp.

---

## 10. Chiến lược chunking

### 10.1. Nguyên tắc đã chốt

Sử dụng **structure-aware hierarchical chunking**.

Không sử dụng fixed-size chunking thuần túy làm phương pháp chính.

Thứ tự ưu tiên điểm cắt:

1. Chapter.
2. Heading cấp 1.
3. Heading cấp 2.
4. Heading cấp 3.
5. Khối quy trình hoặc bảng hoàn chỉnh.
6. Đoạn văn.
7. Danh sách item.
8. Câu.
9. Token, chỉ khi không còn lựa chọn tốt hơn.

Một chunk không được trộn nội dung từ hai section không liên quan chỉ để đạt đủ token.

### 10.2. Hai loại chunk

#### Generation chunk

Dùng để trích knowledge point và sinh câu hỏi.

Cấu hình khởi đầu:

- Target: 600–900 tokens.
- Preferred target: khoảng 750 tokens.
- Soft maximum: 1.000 tokens.
- Hard maximum: 1.200 tokens.
- Overlap: 60–100 tokens, mặc định 80.

#### Retrieval/evidence chunk

Dùng để embedding, tìm evidence hoặc retrieval sau này.

Cấu hình khởi đầu:

- Target: 250–400 tokens.
- Preferred target: khoảng 350 tokens.
- Hard maximum: 450–500 tokens.
- Overlap: 40–60 tokens, mặc định 50.

Generation chunk có thể là parent của nhiều retrieval chunk.

### 10.3. Quy tắc overlap

Overlap không được chỉ copy cứng N token bất kể cấu trúc. Ưu tiên overlap theo:

- Một đoạn hoàn chỉnh trước đó.
- Heading hiện tại.
- Tên quy trình.
- Một hoặc hai list item liên quan.

Không overlap bảng lớn hoặc toàn bộ danh sách nếu làm tăng dữ liệu lặp quá nhiều.

### 10.4. Quy tắc theo loại nội dung

#### Định nghĩa

- Giữ định nghĩa trong một chunk.
- Không ghép thêm nội dung khác chỉ để đạt target.
- Chunk ngắn vẫn hợp lệ nếu là một đơn vị kiến thức hoàn chỉnh.

#### Quy trình/checklist

Giữ chung nếu còn trong hard maximum:

- Tên quy trình.
- Mục đích.
- Phạm vi.
- Chuẩn bị.
- Các bước.
- Theo dõi.
- Tai biến và xử trí.

Nếu quá dài, chia theo nhóm có nghĩa:

- Chuẩn bị.
- Bước 1–5.
- Bước 6–10.
- Theo dõi sau thực hiện.
- Tai biến và xử trí.

Mỗi chunk con phải lặp metadata tên quy trình để tránh mất chủ thể.

#### Danh sách đánh số

- Không cắt ngang một item.
- Giữ số thứ tự gốc.
- Nếu chia danh sách, mỗi chunk cần ghi rõ phạm vi item.

#### Bảng

- Bảng là một element riêng.
- Giữ tên bảng, header, đơn vị và chú thích.
- Nếu bảng dài, chia theo hàng.
- Mỗi chunk bảng phải lặp lại header.
- Không flatten bảng thành chuỗi mất quan hệ cột-hàng.
- Nếu parser không đọc bảng đủ tin cậy, đánh dấu cần review và không sinh câu hỏi tự động từ bảng đó.

#### Hình ảnh/sơ đồ

- Nếu chỉ minh họa: không bắt buộc xử lý.
- Nếu chứa kiến thức: lưu caption, OCR text và liên kết với đoạn văn nhắc tới hình.
- Chưa tự động sinh câu hỏi từ sơ đồ phức tạp nếu không có mô tả text đủ rõ.

### 10.5. Metadata chunk bắt buộc

| Trường | Ý nghĩa |
|---|---|
| chunk_id | ID duy nhất |
| document_id | Tài liệu nguồn |
| section_id | Section nguồn |
| parent_chunk_id | Parent nếu là hierarchical chunk |
| chunk_type | generation hoặc retrieval |
| section_path | Đường dẫn chương/mục/tiểu mục |
| page_start | Trang bắt đầu |
| page_end | Trang kết thúc |
| text | Nội dung chunk |
| token_count | Số token theo tokenizer đã chọn |
| previous_chunk_id | Chunk trước |
| next_chunk_id | Chunk sau |
| source_hash | Hash để phát hiện thay đổi/trùng |
| contains_table | Có bảng hay không |
| contains_warning | Có cảnh báo hay không |
| ocr_used | Có dùng OCR hay không |
| quality_score | Điểm chất lượng chunk |
| needs_review | Có cần kiểm tra thủ công hay không |

### 10.6. Chunk quality gate

Không gửi chunk sang LLM nếu:

- Chỉ chứa header/footer.
- Text quá ngắn và không phải định nghĩa/fact độc lập.
- OCR confidence quá thấp.
- Có quá nhiều ký tự lỗi.
- Table bị mất header.
- Nội dung bị lặp hoàn toàn với chunk khác.
- Không xác định được chủ thể và không thể bổ sung section metadata.

---

## 11. Knowledge point extraction

### 11.1. Lý do phải tách thành stage riêng

Không yêu cầu model “đọc chunk và tạo ngay 10 câu hỏi”. Cách này thường dẫn đến:

- Câu hỏi lặp.
- Hỏi chi tiết không quan trọng.
- Câu không có evidence rõ.
- Câu bị thêm kiến thức ngoài tài liệu.
- Model cố tạo đủ số lượng dù chunk không đủ nội dung.

Pipeline bắt buộc:

```text
Chunk
→ Knowledge points
→ Question candidates
```

### 11.2. Loại knowledge point

Hệ thống cần nhận diện:

- Định nghĩa.
- Thuật ngữ.
- Mục đích.
- Điều kiện.
- Chỉ định.
- Chống chỉ định.
- Ngoại lệ.
- Con số.
- Thời gian.
- Tỷ lệ.
- Liều lượng.
- Trình tự.
- Nguyên nhân.
- Hậu quả.
- So sánh.
- Tiêu chí đánh giá.
- Dấu hiệu nhận biết.
- Tai biến.
- Cách xử trí.
- Quan hệ giữa hai khái niệm.

### 11.3. Dữ liệu knowledge point

Mỗi knowledge point cần lưu:

| Trường | Ý nghĩa |
|---|---|
| knowledge_point_id | ID |
| chunk_id | Chunk nguồn |
| statement | Phát biểu kiến thức ngắn gọn |
| answer_fact | Fact/đáp án cốt lõi |
| evidence_text | Câu/đoạn nguồn chính xác |
| importance | low, medium, high |
| knowledge_type | definition, procedure, warning... |
| suggested_question_types | Loại câu phù hợp |
| suggested_difficulty | Độ khó phù hợp |
| generation_eligible | Có nên sinh câu hỏi không |
| exclusion_reason | Lý do không sinh nếu có |

### 11.4. Quy tắc số lượng

Không đặt cứng số knowledge point theo chunk.

Model có thể trả về 0 knowledge point nếu chunk không có kiến thức kiểm tra độc lập.

Các knowledge point quá giống nhau trong cùng chunk phải được gộp hoặc đánh dấu liên quan.

---

## 12. Tạo câu hỏi

### 12.1. Loại câu hỏi phiên bản đầu

#### Single choice

- Mặc định 4 lựa chọn.
- Đúng chính xác một đáp án tốt nhất.
- Các distractor cùng kiểu dữ liệu và hợp ngữ cảnh.
- Không dùng đáp án “tất cả đều đúng” hoặc “cả A và B” trong MVP.

#### True/False

- Phát biểu phải rõ ràng.
- Không dùng phủ định kép.
- Nếu false, phần giải thích phải chỉ ra nội dung đúng.

#### Short answer

- Câu trả lời ngắn, xác định được từ evidence.
- Có danh sách accepted answer/keyword nếu cần.

### 12.2. Số câu theo mật độ nội dung

Mặc định gợi ý:

| Nội dung | Số câu ứng viên |
|---|---:|
| Định nghĩa ngắn | 1–2 |
| Lý thuyết thông thường | 2–4 |
| Quy trình | 3–8 |
| Bảng rõ ràng | 2–6 |
| Chỉ định/chống chỉ định | 2–5 |
| Cảnh báo/tai biến | 2–5 |
| Nội dung chung chung | 0–1 |
| Reference/header/footer | 0 |

Đây là giới hạn hướng dẫn, không phải quota bắt buộc.

### 12.3. Độ khó

#### Dễ

- Trả lời bằng một fact trực tiếp.
- Evidence nằm trong một đoạn ngắn.
- Chủ yếu recall.

#### Trung bình

- Cần hiểu quan hệ hoặc trình tự trong cùng chunk.
- Có thể yêu cầu phân biệt hai khái niệm gần nhau.
- Distractor hợp lý hơn.

#### Khó

- Cần kết hợp nhiều câu hoặc 2–3 chunk cùng section.
- Có thể là tình huống ứng dụng.
- Không được dựa vào kiến thức ngoài tài liệu nếu hệ thống đang ở chế độ source-grounded.

#### Rất khó

Chưa là mặc định ở MVP. Chỉ thực hiện khi đã có:

- Section summary.
- Retrieval multi-hop.
- Validation mạnh.
- Benchmark chất lượng.

### 12.4. Quy tắc nội dung câu hỏi

Câu hỏi phải:

- Tự đứng độc lập.
- Nêu rõ chủ thể.
- Không dùng “nội dung trên”, “quy trình này”, “trường hợp trên” nếu thiếu ngữ cảnh.
- Không chứa đáp án trong stem.
- Không hỏi kiến thức không xuất hiện hoặc không suy ra trực tiếp từ source.
- Không mơ hồ về thời gian, đối tượng hoặc điều kiện.
- Không có nhiều hơn một đáp án đúng.
- Giữ nguyên thuật ngữ y khoa quan trọng.
- Viết tiếng Việt tự nhiên.
- Tránh câu quá dài không cần thiết.

### 12.5. Quy tắc distractor

Distractor phải:

- Cùng loại với đáp án đúng.
- Có độ dài tương đối cân bằng.
- Hợp lý nhưng sai theo tài liệu.
- Không vô lý hoặc khác hẳn category.
- Không tạo đáp án đúng thứ hai.
- Không chỉ thay đổi một ký tự hoặc lỗi chính tả.
- Không sử dụng thông tin nguy hiểm như lời khuyên y tế ngoài nguồn.

Nguồn tạo distractor ưu tiên:

1. Các fact gần nghĩa trong cùng section.
2. Các giá trị cùng loại nhưng khác đáp án.
3. Các bước lân cận trong quy trình.
4. Biến thể do model tạo nhưng phải qua validation.

---

## 13. Hợp đồng đầu ra chuẩn hóa

Mỗi question candidate cần có tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| question_id | ID |
| job_id | Job sinh câu |
| document_id | Tài liệu nguồn |
| knowledge_point_id | Knowledge point nguồn |
| question_type | single_choice, true_false, short_answer |
| content | Nội dung câu hỏi |
| options | Danh sách lựa chọn nếu có |
| correct_answer | Đáp án đúng |
| accepted_answers | Dùng cho short answer |
| explanation | Giải thích |
| evidence_text | Evidence chính xác |
| source_chunk_ids | Một hoặc nhiều chunk nguồn |
| section_path | Chương/mục/tiểu mục |
| page_start | Trang bắt đầu |
| page_end | Trang kết thúc |
| requested_difficulty | Mức người dùng yêu cầu |
| assessed_difficulty | Mức hệ thống đánh giá |
| llm_provider | Provider đã dùng |
| llm_model | Model đã dùng |
| prompt_version | Phiên bản prompt |
| validation_status | Kết quả validation |
| duplicate_status | Kết quả dedup |
| quality_score | Điểm tổng hợp |
| review_status | pending, approved, rejected, edited |

Không lưu câu hỏi mà thiếu evidence hoặc source location.

---

## 14. Prompt strategy

### 14.1. Prompt phải được version hóa

Mỗi prompt template cần có:

- Prompt name.
- Version.
- Task type.
- Provider compatibility.
- Date activated.
- Status.
- Changelog.

Question record phải lưu prompt version để audit.

### 14.2. Tách prompt theo task

Không dùng một prompt khổng lồ cho mọi việc.

Tối thiểu có các task:

1. Extract knowledge points.
2. Generate single-choice questions.
3. Generate true/false questions.
4. Generate short-answer questions.
5. Validate answerability.
6. Validate single correct answer.
7. Assess difficulty.
8. Repair invalid output.

### 14.3. JSON output

Khi provider hỗ trợ JSON output:

- Bật chế độ JSON.
- Prompt vẫn phải nói rõ output phải là JSON.
- Kiểm tra `finish_reason` và trường hợp output bị cắt.
- Parse bằng schema validator.
- Không tin rằng JSON hợp lệ đồng nghĩa với nội dung đúng.

Nếu output sai schema:

1. Chạy deterministic repair nếu chỉ lỗi nhỏ.
2. Nếu không sửa được, gọi task repair output.
3. Giới hạn số lần retry.
4. Sau retry vẫn lỗi thì đánh dấu chunk failed, không bỏ cả job.

### 14.4. Tối ưu context cache

Đặt phần ổn định ở đầu request:

1. System instruction cố định.
2. Quy tắc chuyên môn chung.
3. Output schema.
4. Task instruction.
5. Section metadata.
6. Chunk thay đổi.

Không thêm timestamp hoặc ID ngẫu nhiên vào phần đầu prompt nếu không cần, vì làm giảm khả năng cache hit.

---

## 15. Validation pipeline

### 15.1. Nguyên tắc

LLM tạo câu hỏi không được tự xác nhận chất lượng duy nhất. Validation phải gồm cả rule deterministic và LLM judge.

### 15.2. Deterministic validation

Kiểm tra tối thiểu:

- Đủ trường bắt buộc.
- Question không rỗng.
- Evidence không rỗng.
- Evidence tồn tại trong hoặc gần source chunk.
- Single choice có đúng số option theo cấu hình.
- Option key không trùng.
- Correct answer trỏ tới option hợp lệ.
- Không có option trùng text sau normalize.
- True/False có answer hợp lệ.
- Độ dài câu hỏi và option trong giới hạn.
- Không có placeholder.
- Không có HTML/script không mong muốn.
- Không có PII đã bị cấm.
- Không có “theo đoạn văn trên” nếu context không đi kèm câu hỏi.

### 15.3. Source grounding validation

Cần xác định:

- Câu hỏi có trả lời được hoàn toàn từ source không.
- Correct answer có được source hỗ trợ không.
- Explanation có thêm fact ngoài source không.
- Evidence có thực sự liên quan hay chỉ trùng từ khóa.

Nếu answer fact không xuất hiện trực tiếp nhưng có thể suy ra, phải đánh dấu `inference_required = true`.

### 15.4. Multiple-correct-answer validation

Đối với single choice:

- Đánh giá từng option độc lập dựa trên source.
- Nếu có từ hai option đúng hoặc có thể đúng, loại hoặc sửa câu.
- Nếu tất cả distractor quá rõ ràng, giảm quality score.

### 15.5. Difficulty validation

Difficulty không chỉ dựa trên model tự khai báo. Có thể dùng feature:

- Số evidence span cần thiết.
- Số chunk cần đọc.
- Recall hay reasoning.
- Độ giống giữa distractor và đáp án.
- Độ dài câu hỏi.
- Số bước suy luận.

Requested difficulty và assessed difficulty phải được lưu riêng.

### 15.6. Quality score

Điểm tổng hợp có thể gồm:

- Source grounding.
- Answer correctness.
- Single-answer confidence.
- Clarity.
- Distractor quality.
- Difficulty fit.
- OCR/source quality.
- Duplicate risk.

Trọng số phải cấu hình được và được điều chỉnh sau benchmark.

Các câu dưới ngưỡng không được tự động đưa vào danh sách review chính; có thể vào nhóm `LOW_QUALITY` để kiểm tra riêng.

---

## 16. Kiểm tra trùng bằng E5-small

### 16.1. Model đã chốt

Tiếp tục sử dụng:

- `intfloat/multilingual-e5-small`

Vai trò:

- Embedding câu hỏi.
- So sánh semantic similarity.
- Phát hiện câu gần trùng trong cùng job, cùng tài liệu và toàn question bank.

E5 không dùng để sinh câu hỏi.

### 16.2. Hai lớp dedup

#### Lớp 1: Text dedup

- Exact match.
- Normalized exact match.
- Fuzzy string match.

Normalization ở đây chỉ áp dụng để so sánh, không thay đổi bản câu hỏi lưu chính thức:

- Lowercase.
- Trim.
- Chuẩn hóa khoảng trắng.
- Chuẩn hóa một số dấu câu.

#### Lớp 2: Semantic dedup

So sánh embedding với:

1. Các câu vừa sinh trong cùng chunk.
2. Các câu trong cùng document/job.
3. Các câu trong cùng chapter/section.
4. Toàn bộ question bank phù hợp scope.

### 16.3. Ngưỡng khởi đầu

Ngưỡng chỉ là giá trị ban đầu để benchmark:

- `>= 0.94`: gần như trùng, mặc định loại hoặc chọn câu tốt hơn.
- `0.88–0.94`: nghi ngờ trùng, đưa review hoặc áp dụng rule bổ sung.
- `0.82–0.88`: có liên quan; thường vẫn có thể giữ nếu knowledge point khác.
- `< 0.82`: ít khả năng trùng.

Không hard-code các ngưỡng này. Lưu trong configuration và hiệu chỉnh trên dữ liệu được gắn nhãn.

### 16.4. Không chỉ dựa vào embedding

Hai câu có thể giống cấu trúc nhưng hỏi hai knowledge point khác nhau. Dedup decision nên xét thêm:

- Answer similarity.
- Knowledge point ID/type.
- Section.
- Evidence overlap.
- Entity/number được hỏi.

Nếu câu giống nhau nhưng đáp án khác do source mâu thuẫn, không tự động giữ cả hai; đánh dấu source conflict.

### 16.5. Lưu duplicate result

Mỗi candidate cần lưu:

- Similar question ID.
- Similarity score.
- Scope so sánh.
- Decision.
- Decision reason.
- Rule hoặc model version.

---

## 17. Paraphrase trong pipeline

Model paraphrase đã chọn cho chức năng riêng:

- `ngwgsang/vietquill-vit5-base-tsubaki` làm candidate local hiện tại qua package `vietquill`.

Ghi chú: không có repo chính thức đang dùng tên `ngwgsang/vietquill-base` trong triển khai hiện tại. Nếu muốn đổi model VietQuill khác, phải ghi rõ repo ID và smoke test tiếng Việt có dấu.

Trong tính năng tạo bộ câu hỏi, paraphrase không phải stage bắt buộc cho mọi câu. Chỉ dùng khi:

- Câu đúng về nội dung nhưng diễn đạt chưa tự nhiên.
- Cần tạo biến thể nhưng vẫn giữ knowledge point.
- Cần tránh lặp cấu trúc trong cùng bộ câu hỏi.

Sau paraphrase phải chạy lại:

- Source grounding validation.
- E5 similarity với câu gốc.
- Dedup với question bank.

Không paraphrase đáp án hoặc thuật ngữ chuyên môn một cách không kiểm soát. Nếu paraphrase cả đáp án, phải chạy lại validation và giữ đúng đáp án đúng.

---

## 18. Human review workflow

### 18.1. Nguyên tắc

Tất cả câu AI sinh trong MVP phải ở trạng thái `PENDING_REVIEW`.

Reviewer có thể:

- Approve.
- Edit and approve.
- Reject.
- Request regeneration.
- Mark duplicate.
- Mark source incorrect.
- Change difficulty.

### 18.2. Thông tin cần hiển thị cho reviewer

- Câu hỏi.
- Các option.
- Đáp án đúng.
- Giải thích.
- Evidence highlight.
- Tên tài liệu.
- Trang.
- Section path.
- Source chunk context.
- Difficulty requested/assessed.
- Quality score.
- Duplicate warning.
- Provider/model.
- Validation warnings.

### 18.3. Audit

Lưu:

- Ai review.
- Thời gian.
- Nội dung trước/sau sửa.
- Lý do từ chối.
- Các warning bị override.

Dữ liệu review nên được dùng sau này để benchmark prompt/model.

---

## 19. Bảo mật và quyền riêng tư

### 19.1. Phân loại tài liệu

Mỗi document cần có data policy:

- `PUBLIC`
- `INTERNAL_CLOUD_ALLOWED`
- `CONFIDENTIAL_LOCAL_ONLY`

Provider routing phải tuân theo policy.

### 19.2. API key

- Chỉ lưu qua environment/secret manager.
- Không commit.
- Không trả về frontend.
- Không ghi log.
- Có khả năng rotate.

### 19.3. PII redaction

Trước cloud request:

- Phát hiện PII.
- Redact hoặc pseudonymize phần không cần thiết.
- Lưu mapping chỉ khi nghiệp vụ bắt buộc và ở khu vực an toàn.

### 19.4. Logging

Không log toàn bộ chunk trong production mặc định.

Log nên chứa:

- Request ID.
- Job ID.
- Chunk ID.
- Provider/model.
- Token usage.
- Latency.
- Status/error code.
- Retry count.
- Hash hoặc excerpt ngắn đã mask nếu cần debug.

---

## 20. Retry, idempotency và lỗi

### 20.1. Idempotency

Mỗi task cần idempotency key dựa trên:

- Document version.
- Chunk source hash.
- Task type.
- Prompt version.
- Model/provider configuration.
- Requested question settings.

Nếu cùng key đã hoàn thành thành công, không gọi lại model trừ khi người dùng yêu cầu regenerate.

### 20.2. Retry

Retry với exponential backoff cho:

- Timeout.
- Rate limit.
- Temporary provider error.
- Network error.

Không retry vô hạn.

Lỗi nội dung như invalid JSON xử lý bằng repair/retry riêng, không dùng network retry mù quáng.

### 20.3. Partial completion

Một số chunk lỗi không làm toàn job thất bại.

Job có thể `PARTIALLY_COMPLETED` với:

- Số chunk thành công.
- Số chunk lỗi.
- Danh sách lỗi.
- Khả năng retry chỉ phần lỗi.

### 20.4. Cancel

Nếu người dùng hủy:

- Không tạo task mới.
- Task đang gọi provider có thể hoàn tất nhưng kết quả không được tiếp tục xử lý nếu job đã cancelled.
- Không xóa artifact đã sinh trừ khi có quy trình cleanup.

---

## 21. Cost, token và hiệu năng

### 21.1. Token budget

Mỗi job cần cấu hình:

- Maximum input tokens.
- Maximum output tokens.
- Maximum questions.
- Maximum retries.
- Maximum cloud cost nếu có.

Khi gần vượt budget:

- Dừng sinh thêm.
- Giữ kết quả đã hoàn thành.
- Đánh dấu job partial/budget exceeded.

### 21.2. Input size

Mặc dù model cloud hỗ trợ context dài, vẫn dùng chunk 600–900 tokens cho generation thông thường.

Không gửi toàn bộ tài liệu 200–300 trang trong một request vì sẽ giảm traceability, khó retry và khó kiểm soát coverage.

### 21.3. Concurrency

- Cloud: có worker pool với giới hạn concurrency và rate limit.
- Local laptop: mặc định 1 inference request tại một thời điểm.
- Không song song quá mức làm tràn RAM hoặc vượt rate limit.

### 21.4. Usage metrics

Lưu theo từng LLM call:

- Prompt tokens.
- Cached input tokens nếu provider trả về.
- Completion tokens.
- Total tokens.
- Latency.
- Model.
- Task type.
- Success/failure.
- Estimated cost.

---

## 22. Coverage và phân bổ câu hỏi

### 22.1. Coverage report

Sau khi xử lý, hệ thống cần có báo cáo:

- Tổng section.
- Section có knowledge point.
- Section đã sinh câu hỏi.
- Section không có câu hỏi và lý do.
- Số câu theo chapter.
- Số câu theo difficulty.
- Số câu theo type.
- Số câu bị loại do validation.
- Số câu bị loại do duplicate.

### 22.2. Tránh thiên lệch đầu tài liệu

Không chỉ lấy N chunk đầu tiên.

Nếu người dùng đặt giới hạn số câu, phân bổ theo:

1. Importance của section/knowledge point.
2. Độ dài hoặc mật độ kiến thức.
3. Coverage toàn tài liệu.
4. Loại nội dung quan trọng như cảnh báo, quy trình, chống chỉ định.

Có thể dùng quota theo chapter nhưng không bắt buộc mỗi chapter có số câu bằng nhau.

---

## 23. Database/domain entities đề xuất

Không bắt buộc tên bảng y hệt, nhưng domain cần thể hiện các entity sau:

### Document

- Metadata file.
- Version.
- Hash.
- Language.
- Page count.
- Data policy.
- Extraction status.

### DocumentSection

- Tree structure.
- Heading.
- Page range.
- Order.

### DocumentElement

- Element type.
- Text.
- Page/order.
- Extraction metadata.

### DocumentChunk

- Chunk type.
- Section path.
- Text.
- Token count.
- Quality flags.

### GenerationJob

- Requested settings.
- Status/progress.
- Provider policy.
- Budget.
- Error summary.

### KnowledgePoint

- Statement.
- Fact.
- Evidence.
- Importance/type.

### QuestionCandidate

- Question content/type.
- Answer/explanation.
- Difficulty.
- Quality/review status.

### QuestionOption

- Key.
- Text.
- Correct flag hoặc liên kết correct answer.
- Order.

### QuestionEvidence

- Chunk.
- Page.
- Section.
- Evidence text/span.

### ValidationResult

- Validation type.
- Pass/fail.
- Score.
- Issues.
- Validator version.

### DuplicateMatch

- Candidate.
- Matched question.
- Similarity.
- Decision.

### LLMCallLog

- Provider/model.
- Task.
- Token/cost/latency.
- Prompt version.
- Status.

### ReviewHistory

- Reviewer.
- Action.
- Before/after.
- Reason.

---

## 24. API boundary ở mức thiết kế

### 24.1. Spring Boot → AI Service

Cần các capability sau, endpoint cụ thể agent tự đặt theo convention dự án:

- Submit document processing job.
- Read job status/progress.
- Cancel job.
- Retry failed stages/chunks.
- Request regeneration cho question hoặc section.
- Retrieve chunks/knowledge points/questions phục vụ review/debug.

### 24.2. Callback hoặc polling

Chọn một trong hai:

- Spring Boot polling AI Service.
- AI Service callback về Spring Boot khi stage hoàn tất.

MVP có thể polling để đơn giản, nhưng trạng thái phải persistent. Không dựa vào memory process.

### 24.3. Provider interface

LLM provider cần hỗ trợ ở mức logic:

- Generate structured output.
- Thinking on/off nếu provider hỗ trợ.
- Model selection.
- Timeout.
- Retry metadata.
- Token usage.
- Provider raw error normalization.

Business layer không được phụ thuộc kiểu response riêng của DeepSeek/Ollama.

---

## 25. Configuration

Các giá trị sau phải cấu hình được:

### Document processing

- Supported file types.
- Max file size.
- Max page count.
- OCR languages.
- OCR confidence threshold.
- Parser strategy.

### Chunking

- Generation target/max tokens.
- Retrieval target/max tokens.
- Overlap.
- Minimum useful text length.
- Table handling.

### Generation

- Provider mặc định.
- Model theo task.
- Temperature.
- Max output tokens.
- Question count limits.
- Allowed question types.
- Allowed difficulties.

### Validation

- Quality score threshold.
- Max repair retries.
- Evidence matching threshold.

### Dedup

- E5 model path.
- Batch size.
- Duplicate thresholds.
- Scope.

### Operations

- Concurrency.
- Rate limit.
- Job timeout.
- Cost limit.
- Retry policy.

---

## 26. Testing strategy

### 26.1. Unit test

- Text cleanup.
- Header/footer removal.
- Heading detection.
- Section tree.
- Chunk boundary.
- Table split.
- Token count.
- Schema validation.
- Correct answer validation.
- Duplicate normalization.
- Provider response normalization.
- Idempotency key.

### 26.2. Integration test

- PDF text → chunks.
- PDF scan → OCR → chunks ở phase hardening hoặc integration environment có OCR sẵn.
- Chunk → DeepSeek mock/real test environment → knowledge points.
- Knowledge point → questions.
- Questions → validation → E5.
- Spring Boot ↔ AI Service.
- Retry/partial failure.

### 26.3. Golden dataset

Tạo bộ dữ liệu benchmark nội bộ gồm tối thiểu:

- 5–10 tài liệu hoặc section đại diện.
- Khoảng 200–500 question candidates được chuyên gia/người dùng gắn nhãn.

Nhãn cần có:

- Đúng/sai.
- Có bám nguồn không.
- Có đúng một đáp án không.
- Difficulty thực tế.
- Có trùng không.
- Distractor có tốt không.
- Có cần sửa không.

Golden dataset dùng để:

- Chọn prompt.
- So sánh Flash/Pro/local.
- Hiệu chỉnh E5 threshold.
- Đánh giá regression khi thay model.

### 26.4. Benchmark cloud vs local

Cùng một input và prompt logical, đo:

- Tỷ lệ JSON hợp lệ.
- Tỷ lệ câu bám nguồn.
- Tỷ lệ một đáp án đúng.
- Tỷ lệ reviewer approve không sửa.
- Latency.
- Chi phí.
- RAM/CPU local.

Không chọn local chỉ dựa vào việc “chạy được”.

---

## 27. Tiêu chí nghiệm thu MVP

### 27.1. Document processing

- Nhận được PDF/DOCX hợp lệ.
- Phân biệt được text PDF và scan PDF ở mức sử dụng được.
- Giữ được page metadata.
- Xây dựng được section tree cho tài liệu có heading rõ.
- Không làm mất dấu tiếng Việt.
- Không cắt ngang phần lớn list item/quy trình một cách vô nghĩa.

### 27.2. Chunking

- Generation chunk phần lớn nằm trong target đã cấu hình.
- Không trộn section không liên quan.
- Có section path và page range.
- Có parent-child giữa generation và retrieval chunk.
- Table dài được chia nhưng giữ header.

### 27.3. Generation

- Mỗi câu có source/evidence.
- Structured output parse được.
- Câu tiếng Việt rõ ràng.
- Single choice có đúng một đáp án sau validation.
- Có thể chọn type và difficulty.
- Có thể dùng DeepSeek provider.
- Có thể đổi sang local provider bằng configuration mà không sửa pipeline core.

### 27.4. Validation và dedup

- Invalid output không làm crash toàn job.
- Có rule validation trước khi lưu.
- Có E5 semantic dedup.
- Lưu duplicate match và score.
- Câu chất lượng thấp không tự publish.

### 27.5. Review và audit

- Reviewer thấy được source page/section/evidence.
- Có approve/edit/reject.
- Lưu lịch sử sửa.
- Lưu model và prompt version.

### 27.6. Operations

- Có progress.
- Có retry chunk lỗi.
- Có partial completion.
- Không log secret.
- Có token usage và estimated cost.

---

## 28. Phân chia phase triển khai

### Phase 1 — Document ingestion và extraction

Mục tiêu:

- Upload/register file.
- Validate.
- Extract PDF/DOCX.
- OCR page cần thiết.
- Lưu element và page metadata.

Chưa gọi LLM ở phase này.

### Phase 2 — Preprocessing và section tree

Mục tiêu:

- Làm sạch.
- Header/footer detection.
- Heading detection.
- Section hierarchy.
- Quality flags.

### Phase 3 — Hierarchical chunking

Mục tiêu:

- Generation chunk.
- Retrieval chunk.
- Metadata đầy đủ.
- Table/list/procedure handling.
- Chunk quality gate.

### Phase 4 — LLM provider abstraction

Mục tiêu:

- Provider interface.
- DeepSeek provider.
- Local provider adapter.
- Structured response normalization.
- Token usage/logging/retry.

Chưa cần tối ưu prompt sâu ở đầu phase.

### Phase 5 — Knowledge point extraction

Mục tiêu:

- Prompt/version.
- Parse và validate output.
- Persist knowledge point.
- Cho phép 0 knowledge point.

### Phase 6 — Question generation

Mục tiêu:

- Single choice.
- True/False.
- Short answer.
- Difficulty dễ/trung bình/khó.
- Evidence và explanation.

### Phase 7 — Validation

Mục tiêu:

- Deterministic rules.
- Grounding validator.
- Single-answer validator.
- Difficulty assessment.
- Quality score.

### Phase 8 — E5 deduplication

Mục tiêu:

- Exact/fuzzy dedup.
- Embedding.
- Similarity search.
- Duplicate decision.
- Configurable threshold.

### Phase 9 — Review workflow

Mục tiêu:

- Danh sách candidate.
- Source viewer.
- Approve/edit/reject/regenerate.
- Audit history.

### Phase 10 — Evaluation và hardening

Mục tiêu:

- Golden dataset.
- Benchmark cloud/local.
- Calibrate thresholds.
- Cost control.
- Performance.
- Security review.

---

## 29. Những lỗi thiết kế agent phải tránh

1. Gửi nguyên tài liệu 300 trang trong một request.
2. Fixed-size chunking thuần túy mà bỏ cấu trúc heading.
3. Dùng E5 để sinh câu hỏi.
4. Sinh trực tiếp số lượng lớn câu hỏi mà không trích knowledge point.
5. Không lưu evidence và page.
6. Tin hoàn toàn vào `confidence` do LLM tự khai báo.
7. Chỉ dùng LLM validation mà không có rule deterministic.
8. Hard-code DeepSeek model name trong nhiều service.
9. Gọi cloud cho tài liệu local-only.
10. Log API key hoặc toàn bộ tài liệu nhạy cảm.
11. OCR toàn bộ PDF dù đã có text layer tốt.
12. Xóa từ phủ định trong preprocessing.
13. Cắt ngang bảng/list/procedure tùy tiện.
14. Mọi chunk bắt buộc sinh cùng số câu.
15. Tự publish câu hỏi chưa review.
16. Retry toàn bộ job vì một chunk lỗi.
17. Hard-code E5 threshold mà không benchmark.
18. Cho model tạo distractor nhưng không kiểm tra nhiều đáp án đúng.
19. Không version prompt.
20. Không lưu model/provider/token usage.

---

## 30. Thứ tự ưu tiên khi phải đánh đổi

Khi có xung đột, ưu tiên theo thứ tự:

1. Đúng nguồn.
2. Không làm sai kiến thức chuyên môn.
3. Truy vết được evidence.
4. Đúng một đáp án.
5. Bảo mật dữ liệu.
6. Khả năng review/audit.
7. Chất lượng tiếng Việt.
8. Coverage tài liệu.
9. Tốc độ.
10. Số lượng câu hỏi.

Không hy sinh độ đúng chỉ để tạo nhiều câu hơn.

---

## 31. Quyết định cuối cùng để agent triển khai

### Stack và thành phần

- Backend nghiệp vụ: Java Spring Boot.
- AI orchestration: Python FastAPI service riêng.
- Database: PostgreSQL.
- Cloud LLM mặc định: DeepSeek API.
- Cloud model MVP: `deepseek-v4-flash`.
- Cloud model tác vụ khó/fallback sau MVP: `deepseek-v4-pro` nếu được cấu hình và kiểm soát chi phí.
- Local LLM candidate cho document generation: model instruct/quantized tương thích sau benchmark; chưa bắt buộc trong MVP.
- Duplicate embedding: `intfloat/multilingual-e5-small` local.
- Paraphrase candidate: `ngwgsang/vietquill-vit5-base-tsubaki` local.
- PDF text parser: parser nhanh với text PDF.
- PDF scan/layout-heavy: OCR/layout-aware parser ở phase hardening, không chặn MVP nếu chưa xong.

### Chunking mặc định

- Generation target: 750 tokens.
- Generation soft max: 1.000 tokens.
- Generation hard max: 1.200 tokens.
- Generation overlap: 80 tokens theo boundary có nghĩa.
- Retrieval target: 350 tokens.
- Retrieval hard max: 500 tokens.
- Retrieval overlap: 50 tokens.

### Pipeline mặc định

```text
Extract
→ Clean
→ Section tree
→ Hierarchical chunks
→ Knowledge points
→ Question candidates
→ Deterministic validation
→ LLM validation
→ E5 dedup
→ Human review
→ Approved question bank
```

### Nguyên tắc bắt buộc

- Cloud/local phải đổi được bằng configuration.
- Không gửi cả PDF vào LLM.
- Không lưu câu không có evidence.
- Không publish tự động trong MVP.
- Tất cả threshold và model name phải configurable.
- Mọi kết quả phải audit được theo document, chunk, prompt và model.

---

## 32. Tài liệu kỹ thuật chính thức tham khảo

Các thông tin model/API có thể thay đổi theo thời gian. Agent phải kiểm tra lại tài liệu chính thức khi bắt đầu implementation hoặc trước deployment.

- DeepSeek API Quick Start: https://api-docs.deepseek.com/
- DeepSeek Chat Completion API: https://api-docs.deepseek.com/api/create-chat-completion
- DeepSeek List Models API: https://api-docs.deepseek.com/api/list-models
- Unstructured PDF partitioning: https://docs.unstructured.io/open-source/core-functionality/partitioning
- Qwen3-4B model card: https://huggingface.co/Qwen/Qwen3-4B
- Multilingual E5 Small model card: https://huggingface.co/intfloat/multilingual-e5-small

---

## 33. Definition of Done cho coding agent

Tính năng MVP dùng DeepSeek Flash chỉ được coi là hoàn thành khi:

- Pipeline xử lý được ít nhất một PDF text và một DOCX/TXT đại diện.
- Nếu OCR chưa được triển khai, PDF scan phải được nhận diện và trả trạng thái cần OCR rõ ràng thay vì sinh câu hỏi sai.
- Có section tree và hierarchical chunks kiểm tra được.
- DeepSeek provider hoạt động qua configuration.
- Local provider cho document generation có extension point hoặc mock đầy đủ; model local thật không chặn MVP.
- Knowledge point và question candidate được lưu với evidence.
- Validation loại được output sai schema và câu nhiều đáp án đúng rõ ràng.
- E5 dedup chạy được và trả matched question/score.
- Một chunk lỗi không làm hỏng toàn job.
- Reviewer xem được source và duyệt/sửa/từ chối.
- Prompt/model/version/token usage được audit.
- Có test cho logic quan trọng.
- Không có secret trong repository hoặc log.
- Có tài liệu cấu hình và hướng dẫn chạy cho môi trường development.

---

## 34. Ghi chú căn chỉnh với repo hiện tại

Repo FastAPI hiện tại đã có một phần pipeline document generation demo. Agent triển khai tiếp không nên viết lại từ đầu nếu không cần thiết.

### 34.1. Thành phần đã có

- Upload/list/detail tài liệu qua `/documents`.
- Extract text cho `.txt`, `.md`, `.pdf`, `.docx`.
- Clean text cơ bản: Unicode NFC, whitespace, nối từ bị ngắt dòng, bỏ dòng lặp ngắn.
- Split chunk theo ký tự với overlap.
- `Document`, `DocumentChunk`, `DocumentQuestionJob`, `DocumentQuestionCandidate`.
- Provider document generation:
  - `MockDocumentQuestionGenerator`.
  - `DeepSeekDocumentQuestionGenerator`.
- Review UI cho câu hỏi từ tài liệu.
- Save candidate thành question bank.
- E5/vector duplicate validation.

### 34.2. Cấu hình DeepSeek Flash cho MVP

Trong môi trường development hiện tại, dùng:

```env
GENERATION_PROVIDER=api
GENERATION_API_BASE_URL=https://api.deepseek.com
GENERATION_MODEL=deepseek-v4-flash
```

`GENERATION_API_KEY` chỉ được đặt trong `.env` local hoặc secret manager. Không ghi key vào spec, frontend, log hoặc test snapshot.

### 34.3. Việc cần làm tiếp trong repo này

Thứ tự ưu tiên triển khai trong repo hiện tại:

1. Nâng prompt/schema của `DeepSeekDocumentQuestionGenerator` theo MVP single-choice.
2. Thêm prompt version, model, provider và token/latency metadata cho từng call.
3. Tách provider interface chung cho document generation, nhưng giữ DeepSeek Flash là provider thật duy nhất của MVP.
4. Cải thiện preprocessing và chunking theo hướng section-aware từng bước, không cần nhảy ngay tới OCR/layout-heavy.
5. Thêm bước knowledge point extraction trước question generation nếu chất lượng câu hỏi trực tiếp từ chunk chưa ổn.
6. Cải thiện validation: evidence grounding, one-best-answer, distractor sanity, duplicate scope.
7. Thêm partial failure theo chunk và retry chunk lỗi.

### 34.4. Việc chưa nên làm ngay

- Chưa chuyển document question generation sang Qwen/VietQuill/BARTpho.
- Chưa bắt buộc OCR production-grade nếu tài liệu demo có text layer hoặc DOCX.
- Chưa gửi toàn bộ tài liệu vào DeepSeek một lần.
- Chưa tạo nhiều question type trước khi single-choice đạt chất lượng.
