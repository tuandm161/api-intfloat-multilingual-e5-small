# Demo diễn đạt lại câu hỏi

Ứng dụng FastAPI hỗ trợ quản lý ngân hàng câu hỏi trắc nghiệm, tạo bộ đề,
phát hiện câu hỏi trùng ngữ nghĩa, diễn đạt lại câu hỏi bằng DeepSeek API và
tạo câu hỏi từ tài liệu PDF/DOCX/TXT/MD.

Model embedding mặc định là
[`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small),
được chạy cục bộ qua `sentence-transformers`.

## Chức năng chính

- Quản lý ngân hàng câu hỏi và các câu hỏi cha/con với 108 câu seed demo.
- Tạo bộ đề và thêm câu hỏi từ ngân hàng.
- Chặn hai câu trùng nội dung hoặc trùng ngữ nghĩa trong cùng một bộ đề.
- Cho phép các câu tương tự cùng tồn tại trong ngân hàng câu hỏi.
- Tạo, đánh giá, chỉnh sửa, duyệt hoặc từ chối câu diễn đạt lại bằng API.
- Upload tài liệu, tách chunk, sinh câu hỏi đề xuất và duyệt trước khi lưu.
- Lưu embedding 384 chiều và tìm kiếm bằng cosine similarity.
- Xuất dữ liệu JSON/CSV, xem audit log và reset dữ liệu demo.

## Yêu cầu

- Python `3.12`.
- Git.
- Khoảng 2 GB dung lượng trống cho môi trường Python, PyTorch và model E5.
- Internet trong lần cài dependency và lần đầu tải model.

Các lệnh bên dưới sử dụng Windows PowerShell. Với macOS/Linux, xem phần
[Lệnh cho macOS/Linux](#lệnh-cho-macoslinux).

## Cài đặt sạch trên Windows

### 1. Clone repository

```powershell
git clone <URL_REPOSITORY>
cd paraphase-question-bank
```

Nếu đã có source code, chỉ cần mở PowerShell tại thư mục chứa `README.md`.

### 2. Tạo virtual environment

```powershell
py -3.12 -m venv .venv
```

Kích hoạt môi trường:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script, chạy một lần trong cửa sổ hiện tại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Cài dependency

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Thư mục `.venv` có thể lớn hơn 1 GB do PyTorch và các thư viện ML. Đây là bình
thường và `.venv` đã được loại khỏi Git bằng `.gitignore`.

### 4. Tạo file cấu hình

```powershell
Copy-Item .env.example .env
```

Cấu hình mặc định trong `.env` sử dụng:

```env
GENERATION_PROVIDER=mock
GENERATION_API_BASE_URL=https://api.deepseek.com
GENERATION_MODEL=deepseek-v4-flash
GENERATION_FALLBACK_MODEL=deepseek-v4-pro

EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-small
EMBEDDING_PROVIDER=real_e5
EMBEDDING_DIMENSION=384
```

Không commit file `.env` vì file này có thể chứa API key. Chỉ commit
`.env.example`.

Để dùng DeepSeek thật cho paraphrase và tạo câu hỏi từ tài liệu:

```env
GENERATION_PROVIDER=api
GENERATION_API_KEY=<DEEPSEEK_API_KEY_CUA_BAN>
```

Nếu chưa có key, giữ `GENERATION_PROVIDER=mock` để chạy demo offline.

### 5. Chạy ứng dụng

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Lần khởi động đầu tiên có thể mất vài phút vì Hugging Face cần tải model E5.
Những lần sau model được đọc từ cache trên máy.

Khi terminal hiển thị `Application startup complete`, mở:

- Ngân hàng câu hỏi: <http://127.0.0.1:8000/questions>
- Bộ đề: <http://127.0.0.1:8000/exams>
- Tài liệu: <http://127.0.0.1:8000/documents>
- Lịch sử diễn đạt lại: <http://127.0.0.1:8000/paraphrase-jobs>
- Hướng dẫn demo: <http://127.0.0.1:8000/demo-guide>
- Swagger API: <http://127.0.0.1:8000/docs>

Dừng server bằng `Ctrl+C`.

## Chạy lại project sau khi đã cài

Mỗi lần mở terminal mới, chỉ cần:

```powershell
cd <DUONG_DAN_DEN_PROJECT>
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

Không cần cài lại dependency hoặc tải lại model nếu `.venv` và cache model vẫn
còn trên máy.

## Chế độ nhẹ, không tải model E5

Nếu máy yếu hoặc chỉ cần xem giao diện, đổi dòng sau trong `.env`:

```env
EMBEDDING_PROVIDER=mock_deterministic
```

Hoặc thay trực tiếp bằng PowerShell:

```powershell
(Get-Content .env) `
  -replace 'EMBEDDING_PROVIDER=real_e5', 'EMBEDDING_PROVIDER=mock_deterministic' |
  Set-Content .env
```

Chế độ mock chạy nhanh và không cần tải model, nhưng kết quả tương đồng chỉ phù
hợp để test luồng ứng dụng, không dùng để đánh giá ngữ nghĩa thực tế.

## Luồng tạo câu hỏi từ tài liệu

1. Upload PDF có text, DOCX, TXT hoặc MD tại `/documents`.
2. Backend extract text, clean text và tách thành chunk nhỏ.
3. Mỗi chunk được gửi riêng cho DeepSeek API để sinh câu hỏi JSON.
4. Candidate được kiểm tra format, trích dẫn nguồn và duplicate bằng E5 local.
5. Người dùng duyệt candidate rồi mới lưu vào ngân hàng câu hỏi.
6. Khi lưu, hệ thống tạo embedding E5 và cập nhật local vector index.

PDF scan/ảnh chưa OCR trong phase này. Nếu PDF không trích xuất được text, hệ
thống sẽ đánh dấu `Cần OCR`.

## Dữ liệu và database

Ứng dụng sử dụng SQLite tại `question_paraphrase.db`. Khi khởi động, ứng dụng tự:

1. Tạo các bảng còn thiếu.
2. Thêm 108 câu hỏi mẫu nếu chưa tồn tại, gồm 100 câu từ `question.md`.
3. Tạo embedding và dựng lại local vector index.

Reset toàn bộ dữ liệu demo:

```powershell
python -m scripts.reset_demo
```

Các lệnh dữ liệu khác:

```powershell
# Thêm các seed còn thiếu
python -m scripts.seed_data

# Tạo lại embedding và vector index
python -m scripts.reindex_embeddings
```

File database đã được `.gitignore` bỏ qua. Mỗi máy sẽ tự tạo database riêng khi
chạy ứng dụng.

## Chạy test

```powershell
python -m pytest -q
```

Test sử dụng embedding provider giả lập để chạy ổn định và không phải tải model
E5. Test cũng không gọi DeepSeek thật; các API response được giả lập.

## Lệnh cho macOS/Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

## Cấu trúc thư mục

```text
app/                FastAPI, nghiệp vụ, template và static files
app/modules/documents/
                    Upload, extract, chunk và sinh câu hỏi từ tài liệu
scripts/            Script seed, reset và reindex
seed_data/          Dữ liệu câu hỏi mẫu
tests/              Unit, integration và end-to-end tests
.env.example        Cấu hình mẫu được phép commit
requirements.txt    Dependency Python
```

Các file/thư mục cục bộ như `.venv`, `.env`, database, cache Python và model ML
không được đưa lên Git.

## Xử lý lỗi thường gặp

### Không tìm thấy Python 3.12

Kiểm tra các phiên bản đã cài:

```powershell
py --list
```

Sau khi cài Python 3.12, chạy lại `py -3.12 -m venv .venv`.

### Port 8000 đang được sử dụng

Chạy bằng port khác:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

Sau đó mở <http://127.0.0.1:8001/questions>.

### Virtual environment bị lỗi

Xóa `.venv`, tạo lại và cài dependency. Thao tác này không xóa source code:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Model E5 không tải được

Kiểm tra kết nối Internet rồi chạy lại server. Để tiếp tục test giao diện ngay,
chuyển `EMBEDDING_PROVIDER` trong `.env` thành `mock_deterministic`.

### DeepSeek API báo lỗi hoặc chưa cấu hình

Kiểm tra `.env`:

```env
GENERATION_PROVIDER=api
GENERATION_API_KEY=<DEEPSEEK_API_KEY_CUA_BAN>
```

Nếu chỉ muốn chạy app không gọi API, đổi lại `GENERATION_PROVIDER=mock`.

## Lưu ý

- Điểm tương đồng E5 không đảm bảo câu hỏi đúng về chuyên môn y khoa.
- Câu diễn đạt lại và câu hỏi sinh từ tài liệu vẫn cần con người duyệt trước khi sử dụng.
- Ngưỡng phát hiện trùng cần được hiệu chỉnh thêm bằng dữ liệu thực tế.
- Local vector index phù hợp với demo; hệ thống lớn nên dùng vector database.
