# Tastly — Kế hoạch Frontend

Bóc tách trang chủ (ảnh mockup tay của bạn) thành từng module UI, kèm data/API cần nối (xem [../backend/BACKEND_PLAN.md](../backend/BACKEND_PLAN.md)) và một số module gợi ý thêm mà mockup hiện chưa có nhưng nên có để hệ thống chạy được hết flow ở backend plan. Xem tổng quan toàn dự án ở [PLAN.md](../../PLAN.md).

## 1. Stack & routes

- Next.js (App Router) + TypeScript + TailwindCSS.
- Gọi backend qua `lib/api.ts` (fetch wrapper, `credentials: 'include'` để cookie `anon_id` tự gửi kèm).

Routes:
| Route | Trang | Có trong mockup? |
|---|---|---|
| `/` | Trang chủ | ✅ (ảnh gửi) |
| `/explore` | Khám phá món | Chỉ có nav link, chưa có UI — gợi ý ở mục 3 |
| `/search` | Tìm món (kết quả tìm kiếm/chat) | Chỉ có nav link, chưa có UI — gợi ý ở mục 3 |
| `/restaurant/[id]` | Chi tiết quán | Chưa có — gợi ý ở mục 3 |
| `/favorites` | Món yêu thích | Nút "Tìm món yêu thích" trỏ tới đây, chưa có UI — gợi ý ở mục 3 |
| `/contact` | Liên hệ | Chỉ có nav link, nội dung tĩnh |

## 2. Module có trong mockup (Trang chủ)

### 2.1 Header
- **UI**: logo + tagline, nút "Chọn vị trí ⌄", nav (Trang chủ/Khám phá món/Tìm món/Liên hệ), toggle VI/EN, nút "🎲 Lắc món", icon tài khoản.
- **Data/API**: location đã chọn lưu vào `GlobalFilterContext`, gửi kèm mọi lần gọi `/api/search`. Nút "Lắc món" scroll xuống hoặc mở modal của module Spin (2.5) — không cần route riêng.
- **Gợi ý bổ sung nhỏ**: `LocationPicker` nên có autocomplete quận/phường thật (hiện là label tĩnh trong ảnh).

### 2.2 Top Notice Bar
- **UI**: 2 dòng nhắc nhở "Hẹn tại quán công cộng" / "Giữ riêng tư vị trí tìm kiếm".
- **Data/API**: tĩnh, không cần API. Có thể thêm nút "x" đóng lại + lưu `localStorage` để khỏi hiện lại (per-viewer, không cần backend).

### 2.3 Hero Section
- **UI**: badge "GỢI Ý ẨM THỰC", H1 "Hôm nay ăn gì bạn ơi?", mô tả, 2 nút CTA ("Khám phá ngay" → `/explore`, "Tìm món yêu thích" → `/favorites`), dãy category chip (Tất cả/Phở & Bún/Cơm & Xôi/Bánh mặn/Món lẩu/Ăn vặt/Cuốn & Bánh).
- **Data/API**: click chip → `POST /api/search` với `form.food_tags=[tag]`, `message=""` (theo mục 3.1 backend plan) → cập nhật `TrendingSection` bên dưới bằng kết quả đã lọc thay vì trending mặc định.
- **State**: `selectedCategory` trong `GlobalFilterContext`.

### 2.4 Trending Section ("Đang hot hôm nay")
- **UI**: heading + "Xem tất cả→", grid 4 `DishCard` (ảnh, badge category, tên món, tên quán, badge rating, badge giá).
- **Data/API**: `GET /api/trending` khi chưa filter; khi có category/chat filter thì dùng `results` từ `/api/search` (component dùng chung 1 `DishCard`, chỉ đổi nguồn data).
- **"Xem tất cả →"**: điều hướng `/explore`.

### 2.5 Featured Banner ("Món nổi bật tuần này")
- **UI**: ảnh full-width, tag "✨ Món nổi bật tuần này", tên món, mô tả, nút "Xem đánh giá" + rating.
- **Data/API**: `GET /api/featured`. Nút "Xem đánh giá" → `/restaurant/{id}` (mục 3.3).

### 2.6 Spin Section ("Bấm quay là có kèo")
- **UI trái**: heading, mô tả, dãy icon chọn category cho vòng quay (món nước/cay/ngẫu nhiên/đồ uống/chè...), text "Chọn ngẫu nhiên từ N món", nút "🎲 Quay món liền!".
- **UI phải**: card kết quả — badge "Chốt món thần tốc", tên món, ảnh nhỏ, mô tả, link "Khám phá", 2 nút "Chốt món này →" / "↺ Quay lại".
- **Data/API**:
  - Bấm "Quay món liền!" → `POST /api/recommend/spin` với `categories` = icon đang chọn → render `SpinResultCard`.
  - "Chốt món này" → `POST /api/feedback` `action:"choose"` + toast xác nhận.
  - "Quay lại" → gọi lại `/api/recommend/spin` với `exclude_restaurant_ids` thêm quán vừa bị bỏ, log `action:"reject"`.
- **State**: `spinCategories[]`, `excludedIds[]`, `spinResult`.

### 2.7 Mood Section ("Tâm trạng hôm nay?")
- **UI**: heading + mô tả, dãy `MoodChip` (Buồn buồn/Mệt lả/Muốn quẩy/Cuối tháng/Solo traveler/Thèm ăn khuya/Không biết ăn gì), card kết quả (ảnh, "Gợi ý: {mood}", tên món, mô tả, link "Khám phá", "Hoặc thử: X, Y", nút "Tìm quán →").
- **Data/API**: click mood chip → `GET /api/mood?mood=...` → render card. Nút "Tìm quán →" → `POST /api/search` với `form` suy ra từ mood (mục 3.5 backend plan), điều hướng sang `/search` để hiện list đầy đủ.
- **State**: `selectedMood`.

### 2.8 Footer
- **UI**: logo + mô tả, social icon (FB/IG/TikTok — link tĩnh), 4 cột link món ăn theo category, copyright.
- **Data/API**: tĩnh, không cần API. Các link món ăn có thể trỏ `/explore?tag=pho` v.v.

## 3. Module gợi ý thêm (chưa có trong mockup nhưng nên có)

Mockup hiện chỉ là trang chủ — để chạy hết flow đã thiết kế ở backend, cần thêm:

1. **SearchBar / Chat box** — toàn bộ pipeline module 1 ở backend (hiểu prompt tự nhiên "tìm ramen dưới 150k, đừng cay quá") cần 1 input text thật, nhưng mockup chưa có ô nào ngoài category chip. Đề xuất: đặt 1 thanh search/chat trong Hero (dưới 2 nút CTA) hoặc là trang `/search` riêng.
2. **Trang `/explore`** — lưới món đầy đủ có filter sidebar (giá, khoảng cách, cuisine...), phân trang — đích của "Khám phá ngay" và "Xem tất cả→".
3. **Trang `/search`** — hiển thị `results` trả về từ `/api/search`, kèm 1 ô nhập feedback tiếp theo ("A ngon nhưng xa quá...") gọi `POST /api/feedback` (module 8) để tinh chỉnh mà không phải gõ lại từ đầu.
4. **Trang/modal `/restaurant/[id]`** — chi tiết quán, menu, review — đích của việc click `DishCard` hoặc nút "Xem đánh giá".
5. **Trang `/favorites`** — đích thật cho nút "Tìm món yêu thích", danh sách món/quán đã "Chốt món này".
6. **Loading & skeleton state** — cho `TrendingSection`, `SpinResultCard`, `MoodResultCard` khi đang gọi API (tránh giật layout, đặc biệt `/api/recommend/spin` và LLM parse có thể mất 1-2s).
7. **Empty/error state** — khi `/api/search` không ra kết quả hoặc lỗi mạng (mockup chỉ thiết kế happy path).
8. **Toast/notification nhỏ** — xác nhận khi "Chốt món này" hoặc thêm vào favorites thành công.
9. **Mobile nav (hamburger menu)** — mockup chỉ có bản desktop, header hiện tại sẽ vỡ layout ở màn hình nhỏ.
10. **Đóng Top Notice Bar** — cho phép user tắt để đỡ chiếm chỗ sau lần đầu xem.

## 4. Cấu trúc component/folder (đề xuất)

```
frontend/
├── app/
│   ├── layout.tsx            (Header + TopNoticeBar + Footer bọc quanh)
│   ├── page.tsx               (Trang chủ — ghép các section 2.3–2.7)
│   ├── explore/page.tsx
│   ├── search/page.tsx
│   ├── restaurant/[id]/page.tsx
│   ├── favorites/page.tsx
│   └── contact/page.tsx
├── components/
│   ├── layout/ (Header, TopNoticeBar, Footer, LocationPicker, LangToggle)
│   ├── home/   (HeroSection, CategoryChips, TrendingSection, DishCard, FeaturedBanner)
│   ├── spin/   (SpinSection, SpinCategoryIcons, SpinResultCard)
│   ├── mood/   (MoodSection, MoodChip, MoodResultCard)
│   ├── search/ (SearchBar, FeedbackInput, ResultList)   ← module gợi ý mục 3
│   └── common/ (RatingBadge, PriceBadge, Toast, Skeleton, EmptyState)
├── lib/
│   ├── api.ts                (fetch wrapper tới các endpoint trong backend plan)
│   └── filter-context.tsx    (GlobalFilterContext: location, category, mood, spin excludes)
└── FRONTEND_PLAN.md          (file này)
```

## 5. State & data flow

- **Cookie `anon_id`**: backend tự set, frontend không cần quản lý — chỉ cần `fetch(..., { credentials: 'include' })` trong `api.ts`.
- **`GlobalFilterContext`**: giữ `location`, `selectedCategory`, `selectedMood`, `spinExcludedIds`, `lastState` (echo từ response `/api/search` để hiển thị lại khi cần feedback tiếp).
- Mỗi section tự fetch data riêng (trending, featured, mood) — không cần 1 API tổng cho trang chủ, giữ đơn giản.

## 6. Checklist trước khi build

- [ ] Loading/skeleton cho mọi khối gọi API (2.4, 2.6, 2.7).
- [ ] Empty/error state cho search & spin.
- [ ] Responsive: header sập thành hamburger dưới `md`, category chip/mood chip scroll ngang trên mobile.
- [ ] Toggle VI/EN thực sự đổi nội dung (kể cả text trong `MoodChip`, `DishCard` badge).
- [ ] Alt text ảnh món ăn, `aria-pressed` cho chip đang chọn (accessibility cơ bản).
