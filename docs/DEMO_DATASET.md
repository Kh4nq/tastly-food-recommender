# Dataset demo có ràng buộc — 12/10/2026

Theo yêu cầu demo của nhóm, bản đang hoạt động trong `data/processed` và `data/embeddings` là **synthetic_demo**. Vị trí và ID quán giữ từ dữ liệu gốc; tiện ích, thực đơn, giá và dinh dưỡng của thực đơn là giả lập, không phải thông tin đã xác minh.

## Sinh và phát hành

Xử lý tại `mlai-food`, rồi copy sang project chính:

```powershell
python scripts/34-build-coherent-demo-dataset.py --publish
```

Output: `mlai-food/data/releases/ai1-demo-v1/processed`, `embeddings`, `ai1-demo-data.zip`. Bộ có nguồn trước đó được giữ trong `mlai-food/data/releases/ai1-profile-v1` và backup ngay trong `mlai-food-recommender/data/backups/before-coherent-demo-v1` trước khi publish lần đầu.

## Gán thực đơn phù hợp từng quán

Ưu tiên cuisine đã có của quán: Nhật, Hàn, Trung, Thái, Âu. Với quán chưa có nhãn cụ thể, dùng tên và loại hình để chọn một kịch bản demo; không có tín hiệu thì mặc định kịch bản Việt. Nhãn cuisine gốc của quán được giữ riêng, giả định mới nằm ở `demo_menu_cuisine`.

- Quán Nhật chỉ lấy món Nhật: sushi, sashimi, ramen, udon, tempura, teriyaki, edamame và trà Nhật; không ghép phở/cơm tấm.
- Quán Hàn, Trung, Thái, Âu có pool riêng; không chọn ngẫu nhiên từ toàn bộ 4.000 món.
- Quán chay chỉ dùng món chay, kể cả quán có cuisine nước ngoài.
- Café ưu tiên đồ uống/snack/bakery/dessert; bakery và quán kem có pool riêng.
- Tên quán Việt chuyên phở/bún/cơm/bánh mì chọn đúng nhóm món cùng đồ uống.

68 món demo có ID mới `demo:dish:v1:*`. Giữ 4.000 dish ID cũ trong catalog để tương thích, nhưng menu demo chỉ tham chiếu món mẫu đã kiểm soát. Có 173.546 menu ID mới `demo:menu:v1:*`; mapping cũ được giữ trong backup, không dùng ID menu cũ cho một món mới.

## Metadata quán theo kịch bản

Các quy tắc dùng loại hình, cuisine, dấu hiệu trong tên và seed ổn định theo ID:

- Café và nhà hàng theo kịch bản premium có Wi-Fi/AC; hàng nhỏ có xác suất thấp hơn.
- Garden/terrace có ngoài trời; mall/garden/premium có thể có parking. Parking true ghi phạm vi car + motorbike của kịch bản.
- Quiet ưu tiên kịch bản café/premium/garden; family/highchair ưu tiên nhà hàng có quy mô phù hợp.
- Capacity theo nhóm nhà hàng, café, hàng nhỏ; không phải số bàn trống.
- Biến thể giữa các quán dùng seed cố định, nên chạy lại cho cùng ID ra cùng kịch bản. Đây là giả định có quy tắc, không phải suy luận sự thật từ tên.

Mỗi trường có `status=synthetic`, `demo_only=true` và phương pháp sinh. Muốn chỉnh kịch bản, sửa hàm `scenario`, bảng `CATALOG` hoặc block sinh profile trong script 34, rồi chạy lại; không sửa trực tiếp file vector/hash.

## Metadata món và feature của Huy

Mỗi món mẫu có category, meal_role, protein, cooking style, vegetarian, spicy, calories và giá. Calories là ước lượng **một khẩu phần demo**, lấy theo từng món mẫu thay vì một số ngẫu nhiên chung. Trà không đường có thể 0–5 kcal; đây không phải lỗi thiếu metadata.

Metadata trong menu được lấy từ chính dish được tham chiếu. AI1 chuyển calories/category/protein/cooking và spicy vào Candidate; AI3 tính sáu feature như bản sửa trước. Không đổi 15 feature của CatBoost hoặc weights. Các match feature có thể bằng 0 khi state không yêu cầu hoặc nhãn không khớp; không ép mọi feature thành số dương.

## Embedding và kiểm tra

Chỉ tái sử dụng vector cũ khi ID, model và nguyên văn text đưa vào encoder khớp. Món mới được encode thật bằng MiniLM đã cache; mapping menu, source SHA256 và artifact SHA256 được tạo lại cho bộ demo. Không tạo vector ngẫu nhiên hoặc sửa hash để che dữ liệu lệch.

Builder kiểm tra ID, khóa ngoại, cuisine món–quán, món chay, calories giữa menu/dish, profile và checksum embedding trước khi publish. Báo cáo ở `mlai-food/reports/qa/ai1-demo-v1`. Đây là kiểm tra nhất quán của demo, không phải đo chất lượng khuyến nghị ngoài đời.

Loader chỉ nhận synthetic khi manifest ghi rõ `usage=synthetic_demo` và mỗi profile đều `demo_only=true`; release có nguồn vẫn từ chối synthetic. Candidate/ranking giữ cờ demo để quản lý dữ liệu. Theo yêu cầu giao diện của nhóm, API/UI không chèn thông báo giả lập vào câu trả lời. Cảnh báo về ưu tiên chưa khớp hoặc thiếu dữ liệu vẫn được hiển thị khi có.

**Khởi động lại backend sau khi đổi data** vì Retriever được cache. Trên Kaggle dùng code ZIP mới và `ai1-demo-data.zip`; giải nén rồi upload riêng `processed/` + `embeddings/`. Không upload cả thư mục backups. Script 30/31/33 dành cho bản có nguồn, không dùng để tái phát hành demo thành dữ liệu thật.
