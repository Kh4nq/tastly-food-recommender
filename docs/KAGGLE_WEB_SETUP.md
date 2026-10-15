# Chạy web demo trên Kaggle

Notebook thay thế: `dist/kaggle/mlai-runner.ipynb` (cùng nội dung với
`mlai-fullstack-web-kaggle.ipynb`). File không lưu output hoặc Secrets.

## Chuẩn bị

1. Upload bản mới của `dist/kaggle/mlai-fullstack-code.zip` vào Dataset code.
2. Upload `../mlai-food/data/releases/ai1-demo-v1/ai1-demo-data.zip` vào Dataset data.
3. Import notebook, attach hai Dataset đó, bật Internet và GPU nếu bật Qwen.
4. Bật quyền truy cập Secrets: `NGROK_AUTHTOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
   Hai Secret Gemini chỉ cần khi `ENABLE_GEMINI=True`.

Không dùng code ZIP cũ: bản mới phải có `scripts/kaggle_setup.py`. Notebook nhận
cả ZIP và thư mục được Kaggle giải nén. Nếu attach nhiều phiên bản, đặt đường dẫn
`CODE_ARCHIVE` / `DATA_ARCHIVE` cụ thể ở mục 1.

## Chạy

Chạy lần lượt mục **1 đến 8**. Mục 9 xem log; mục 10 dừng server và tunnel sau
khi thử xong. Không chạy mục 10 ngay sau khi vừa nhận link web.
Mục 10 mặc định `STOP_SERVERS=False`, nên **Run All** không tự tắt web.
Đổi thành True và chạy lại mục 10 để dừng.

- Mục 1: kiểm tra checksum code/data và chép `processed`, `embeddings` vào project.
- Mục 2: cấu hình Qwen/Gemini và đọc Secrets. Mặc định bật cả hai.
- Mục 3: tạo venv riêng, cài dependency Python, Node 22, PostgreSQL và `npm ci`.
- Mục 4: tải MiniLM và Qwen base, kiểm tra encode thật, load Qwen NF4 + adapter
  LoRA trên GPU, kiểm tra hash/ID/cuisine và CatBoost. Qwen chỉ tải khi được bật.
- Mục 5: tạo database gắn với hash dataset, seed và đối chiếu số dòng.
- Mục 6: chạy FastAPI 8000 và Next.js 3000, chờ readiness.
- Mục 7: tìm phở/sushi qua frontend và kiểm tra có kết quả; nguồn dataset được kiểm tra ở mục 4.
- Mục 8: mở tunnel port 3000, cập nhật origin, kiểm tra HTTPS/session/reset,
  rồi hiển thị link web.

Thử chat trực tiếp trên web sau khi nhận link. Các probe tìm món không xác minh
chất lượng hội thoại hoặc khả năng đáp ứng của API Gemini. `CHECK_GEMINI=True`
gọi API một lần để kiểm tra model Gemini; mặc định False.

Model tải vào cache `/kaggle/working/tastly-hf`; môi trường riêng ở
`/kaggle/working/tastly-venv`. Không cần restart kernel vì mọi dependency và
server chạy bằng Python của venv. Chi tiết tải/cache model theo
[Hugging Face snapshot_download](https://huggingface.co/docs/huggingface_hub/en/guides/download).

Nếu cell lỗi, dừng tại cell đó và xem log tương ứng trong `PROJECT/kaggle-logs`.
Không upload `.env`, token hoặc `data/backups`. Dataset này dùng dữ liệu giả lập
có ràng buộc cho demo; không phải thông tin quán đã được xác minh.

## Khắc phục lỗi `COPY dishes ... fat: "20.0"` ở mục 5

Schema cũ dùng INTEGER NOT NULL cho `fat/fiber/sugar/protein`. Parquet mới mang
float và 68 món demo chưa có bốn chỉ số này. Schema mới dùng DOUBLE PRECISION
nullable và có ALTER TABLE cho database đã tồn tại; không thay dữ liệu thành 0.
Với phiên Kaggle đang chạy code ZIP cũ, dán nội dung
`dist/kaggle/fix_nutrition_schema.py` vào cell thay mục 5, rồi chạy tiếp mục 6.
Không cần tải model hoặc dựng embeddings lại. Schema không sửa Parquet/hash.
