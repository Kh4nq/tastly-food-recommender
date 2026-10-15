# Tastly — Kế hoạch Backend

Backend nối **Frontend (Next.js) ↔ AI (AI 2 → AI 1 → AI 3) ↔ PostgreSQL**, phục vụ nhiều người dùng cùng lúc. Frontend đọc mục 4–6 để biết cần gọi gì, gửi gì, nhận gì (xem [frontend/FRONTEND_PLAN.md](../frontend/FRONTEND_PLAN.md)).

> Trạng thái: **kế hoạch**. Chưa có HTTP server. Mọi DTO ở mục 5 là đề xuất; sửa ở đây trước, rồi mới code.

## 1. Nguyên tắc

- **Controller mỏng**: chỉ HTTP (validate, cookie, map lỗi). Không chứa logic.
- **Service thuần**: không import FastAPI, psycopg hay module AI cụ thể. Chỉ biết `Protocol`.
- **Port/Adapter**: AI, DB, session đều nằm sau interface; test thay bằng fake, không cần model, DB hay mạng.
- **Giữ ranh giới AI** (theo [AGENTS.md](../../AGENTS.md)): AI 2 parse và quản lý state; AI 1 chỉ nhận state, trả `Candidate[]`; AI 3 nhận state + candidates, trả `RankedResult[]`. Backend không parse prompt, không tự retrieve hay rank.
- **Không đổi `common/schemas.py`**. DTO HTTP nằm riêng trong `backend/api/schemas.py`. Giữ nguyên mọi `restaurant_id`, `menu_item_id`, `dish_id`.
- Import khi khởi động không nạp dataset/model; việc đó làm trong `lifespan`.
- Test chạy offline, không gọi Gemini/OpenAI, không cần API key.

## 2. Kiến trúc

```text
Next.js ──HTTP/JSON──▶ api/  (Controller)
                         │ DTO
                         ▼
                    services/SearchService ... FeedbackService ... CatalogService
                         │
   ┌─────────────────────┼───────────────────┬──────────────────────┐
   ▼                     ▼                   ▼                      ▼
SessionStore        ConversationPort   RecommendationPipeline    CatalogRepo
(port)              (port)             (retrieve→exclude→rank)   (port)
   │                     │                   │                      │
 session_pg /       adapters/ai.py      callable AI1 + AI3     catalog_pg.py
 session_memory     (AI 2 parse+state)  (có sẵn trong repo)    (database.repository)
```

```text
src/backend/
  main.py        # create_app(), lifespan, wiring (composition root)
  settings.py    # đọc env một chỗ (DATABASE_URL, giới hạn, CORS origin, ...)
  ports.py       # Protocol: SessionStore, ConversationPort, CatalogRepo, FeedbackStore
  mappers.py     # RankedResult + dòng DB -> DTO
  api/
    schemas.py   # HTTP DTO (request/response)
    deps.py      # Depends: lấy service, session_id từ cookie
    errors.py    # exception -> error envelope
    routes_search.py  routes_feedback.py  routes_catalog.py  routes_health.py
  services/
    pipeline.py          # RecommendationPipeline (retrieve -> exclude -> rank)
    search_service.py    # use case chính
    feedback_service.py
    catalog_service.py
  adapters/
    ai.py                # AI 2 adapter: threadpool + semaphore + timeout
    session_memory.py    # dev/test
    session_pg.py        # production, nhiều worker dùng chung
    catalog_pg.py        # bọc database.repository
    feedback_pg.py
```

## 3. Luồng `POST /api/search`

1. Controller đọc cookie `anon_id` làm `session_id` (chưa có thì tạo UUID và set cookie). Validate body theo `SearchRequest`.
2. `SearchService` lấy state cũ từ `SessionStore` (có thể rỗng) kèm `version`.
3. `ConversationPort` dựng `UserRequest(session_id, form, message, current_state, previous_results)` rồi gọi `parse_user_input` và `update_state` → `UserPreferenceState` mới.
4. `RecommendationPipeline.search(state, top_k, exclude)`:
   - `retrieve(state, top_k=retrieval_top_k)` — lấy dư, không dùng `top_k`.
   - loại các quán có `restaurant_id` nằm trong `exclude` — **trước khi** rank để không chiếm slot.
   - `rank(state, kept, top_k)` → `RankedResult[]`.
5. `CatalogRepo.get_menu_items_by_ids(menu_item_ids)` hydrate **một query** (đã có thứ tự giữ nguyên như kết quả AI).
6. `mappers` ghép `RankedResult` + dòng DB → `DishResult[]`.
7. Lưu state mới (`UPDATE … WHERE version = :v`), trả `SearchResponse`.

`exclude` là cơ chế cho nút "Quay lại" / "Tìm lại" ở frontend: gửi danh sách `restaurant_id` đã bỏ.

## 4. Endpoint

Tiền tố `/api`. Mọi request frontend phải dùng `credentials: 'include'` để cookie `anon_id` được gửi kèm.

| Method | Path | Mục đích | Phiên bản |
|---|---|---|---|
| POST | `/api/search` | Form và/hoặc chat → danh sách món gợi ý | v1 |
| POST | `/api/feedback` | Ghi hành động người dùng (choose/reject/...) | v1 |
| GET | `/api/restaurants/{id}` | Chi tiết quán + menu (trang `/restaurant/[id]`) | v1 |
| GET | `/api/session` | Lấy lại state hiện tại (reload trang) | v1 |
| DELETE | `/api/session` | Xóa state, bắt đầu tìm lại từ đầu | v1 |
| GET | `/health` | Process còn sống | v1 |
| GET | `/ready` | Đã nạp model và kết nối được DB | v1 |
| GET | `/api/trending`, `/featured` | Cần nguồn dữ liệu popularity (chưa có) | sau |
| POST | `/api/recommend/spin`, GET `/api/mood` | Dựng trên `/api/search` + preset | sau |

## 5. Hợp đồng DTO (đề xuất cho frontend)

### 5.1 `POST /api/search`

Request:

```json
{
  "message": "tìm phở dưới 60k, đừng cay quá",
  "form": {
    "location": { "lat": 21.0285, "lon": 105.8542 },
    "food": ["pho"],
    "cuisine": null,
    "budget_max": 60000,
    "max_distance_km": 3
  },
  "exclude_restaurant_ids": ["R12"],
  "previous_results": [{ "rank": 1, "restaurant_id": "R12", "menu_item_id": "M99" }],
  "top_k": 10
}
```

- Mọi trường đều tùy chọn. `form` dùng đúng tên trường của AI 2 (`food`, `cuisine`, `budget_max`, `max_distance_km`, `location`); **không** phải `food_tags` như FRONTEND_PLAN mục 2.3 đang ghi — frontend cần đổi.
- `session_id` không nằm trong body; lấy từ cookie.
- `previous_results` dùng để AI 2 hiểu "món số 1", "quán đó"; frontend gửi lại danh sách đang hiển thị.
- `top_k` mặc định 10, tối đa do server giới hạn.

Response `200`:

```json
{
  "session_id": "b3f1…",
  "results": [
    {
      "rank": 1,
      "score": 0.87,
      "restaurant_id": "R12",
      "menu_item_id": "M99",
      "dish_id": "D7",
      "restaurant_name": "Phở Thìn - Lò Đúc",
      "dish_name": "Phở bò tái chín",
      "address": "13 Lò Đúc, Hai Bà Trưng, Hà Nội",
      "location": { "lat": 21.01, "lon": 105.85 },
      "price_vnd": 55000,
      "price_is_verified": true,
      "distance_km": 1.2,
      "rating": 4.6,
      "is_vegetarian": false,
      "cuisine": "vietnamese",
      "image_url": null,
      "review_count": null
    }
  ],
  "state": { "...": "UserPreferenceState (echo, frontend lưu để hiển thị chip bộ lọc hiện tại)" }
}
```

Các trường **có thể `null`**, frontend phải có fallback:

- `image_url`, `review_count`: DB hiện **không có**. `DishCard` dùng ảnh placeholder cho đến khi có nguồn dữ liệu.
- `rating`, `distance_km`, `price_vnd`: có thể thiếu theo dữ liệu AI trả về hoặc DB.
- `restaurant_name`, `dish_name`: ưu tiên dòng DB, nếu DB lỗi thì lấy từ `RankedResult`.

Mapping sang `DishCard`: `name = dish_name`, `restaurant = restaurant_name`, `price = price_vnd` (format ở frontend), `rating`, `reviewCount = review_count ?? 0`. `badge` (category) frontend tự suy ra từ `cuisine` bằng bảng của mình.

### 5.2 `POST /api/feedback`

```json
{
  "action": "choose",
  "restaurant_id": "R12",
  "menu_item_id": "M99",
  "rank_position": 1,
  "message": null
}
```

Trả `204`. Backend ghi `FeedbackEvent` vào bảng `feedback_events`. **v1 không** tự diễn giải feedback thành thay đổi state (AI 2 chưa hỗ trợ); muốn tinh chỉnh ("rẻ hơn nữa", "xa quá") thì frontend gửi lại thành `message` ở `/api/search`.

`action` là chuỗi mở; đề xuất dùng thống nhất: `choose`, `reject`, `like`, `dislike`, `view`.

### 5.3 `GET /api/restaurants/{id}`

```json
{
  "restaurant": {
    "restaurant_id": "R12", "name": "Phở Thìn - Lò Đúc", "address": "…",
    "location": { "lat": 21.01, "lon": 105.85 },
    "cuisine": "vietnamese", "opening_hours": "…", "phone": "…", "website": null
  },
  "menu": [
    { "menu_item_id": "M99", "dish_id": "D7", "dish_name": "Phở bò tái chín",
      "price_vnd": 55000, "price_is_verified": true, "is_vegetarian": false }
  ]
}
```

`404` nếu không có quán. Không có review, ảnh hay rating trong DB hiện tại.

### 5.4 `GET /api/session` và `DELETE /api/session`

- `GET` trả `{ "state": {...} | null }`. `DELETE` trả `204` và xóa state; cookie giữ nguyên.

### 5.5 Lỗi (mọi endpoint)

```json
{ "error": { "code": "validation_error", "message": "…", "request_id": "a1b2…" } }
```

| HTTP | `code` | Khi nào | Frontend nên |
|---|---|---|---|
| 422 | `validation_error` | Body sai | Báo lỗi form |
| 404 | `not_found` | Quán không tồn tại | Trang 404 |
| 409 | `session_conflict` | Hai tab cập nhật state cùng lúc | Gọi lại một lần |
| 429 | `rate_limited` | Quá nhiều request | Chờ `Retry-After` |
| 503 | `busy` / `ai_unavailable` | Hàng đợi AI đầy hoặc AI chưa sẵn sàng | Thử lại sau, hiện thông báo |
| 504 | `timeout` | Quá thời gian xử lý | Cho người dùng bấm thử lại |
| 500 | `internal_error` | Lỗi khác | Báo lỗi chung |

Mọi response có header `X-Request-ID`; khi báo lỗi cho team hãy kèm mã này.

## 6. Cookie, CORS, bảo mật

- Cookie `anon_id`: UUID, `HttpOnly`, `SameSite=Lax`, `Secure` khi chạy HTTPS, sống 30 ngày. Đây là `session_id` của AI.
- Dev: Next chạy `http://localhost:3000`, backend `http://localhost:8000`. Backend bật CORS **chỉ** cho origin cấu hình trong env, với `allow_credentials=true` (không dùng `*`). Hoặc cấu hình `rewrites` trong `next.config` để gọi cùng origin và khỏi lo CORS.
- v1 **không có đăng nhập**. Các trang `/login`, `/register`, `/settings` của frontend chưa có API; làm sau và cần bảng `users` (DB chưa có). `user_id` truyền vào AI là `null` ở v1.
- Mọi bí mật (DB, Gemini) chỉ đọc từ biến môi trường. Không log nội dung `message` ở mức INFO.
- Rate limit theo IP/cookie (token bucket trong bộ nhớ) cho `/api/search`.

## 7. Nhiều người dùng và độ ổn định

| Vấn đề | Cách xử lý |
|---|---|
| Nạp model chậm | Nạp **một lần** trong `lifespan`, `/ready` chỉ báo OK sau khi xong |
| AI là code đồng bộ, nặng CPU/GPU | Endpoint `def` (threadpool) hoặc `run_in_threadpool`; không chặn event loop |
| Quá tải GPU/SLM | `Semaphore(N)` quanh bước AI; hết chỗ trong thời gian chờ → `503 busy` |
| Gemini/AI treo | Timeout mỗi bước và tổng; quá hạn → `504`. Thread không kill được nên giữ semaphore đến khi xong |
| Nhiều worker | State nằm ở Postgres (`sessions`), worker nào phục vụ session nào cũng được |
| Hai tab đua nhau | Cột `version`, `UPDATE … WHERE version = :v`; thua → `409`, retry một lần |
| Hết kết nối DB | Pool `max_size` hiện 10/process; `workers × 10 < max_connections` của Postgres |
| DB lỗi | Vẫn trả kết quả AI, tên lấy từ `RankedResult` (degrade), `image_url=null` |
| Quan sát | Log JSON kèm `request_id`, thời gian từng bước (parse/retrieve/rank/hydrate) |

Số worker ban đầu: **1–2**. Mỗi worker giữ một bản model trong RAM. Muốn nhiều hơn thì tách AI thành process riêng (ngoài phạm vi v1).

## 8. Cơ sở dữ liệu cần thêm

Thêm migration trong `database/` (hiện chỉ có `restaurants`, `dishes`, `menu_items`):

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    state JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    action TEXT NOT NULL,
    restaurant_id TEXT,
    menu_item_id TEXT,
    rank_position INTEGER,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Dọn session cũ (ví dụ > 30 ngày) bằng job định kỳ, làm sau. Chỉ lưu `UserPreferenceState`; **không** lưu `relative_updates` (theo hợp đồng AI 2).

## 9. Chạy và cấu hình

Biến môi trường (thêm vào `.env.example`, không commit `.env`): `DATABASE_URL`, `BACKEND_CORS_ORIGINS`, `BACKEND_AI_CONCURRENCY`, `BACKEND_AI_TIMEOUT_S`, `BACKEND_SESSION_STORE=memory|postgres`. Giữ `LOCAL_SLM_ENABLED=false` trừ khi cần.

Dev: `uvicorn backend.main:app --reload --port 8000` (với `--reload` chỉ 1 process). Cần thêm `fastapi`, `uvicorn` (và `httpx` cho test) vào `pyproject.toml`: **thay đổi dependency chung, phải báo team** trước khi merge.

## 10. Thứ tự làm

| # | Việc | Kiểm tra |
|---|---|---|
| 1 | `services/pipeline.py` (`RecommendationPipeline`) | `tests/backend/test_backend_pipeline.py` |
| 2 | `ports.py` + `session_memory.py` | test lưu/đọc/version |
| 3 | `adapters/ai.py` (AI 2 parse + state) | test với parser mock, không gọi provider |
| 4 | `services/search_service.py` | test bằng fake toàn bộ port |
| 5 | `api/schemas.py` + `mappers.py` | test map đủ trường, `null` đúng chỗ |
| 6 | `main.py`, `routes_search.py`, `errors.py` | `TestClient` với service giả |
| 7 | `catalog_pg.py`, `session_pg.py`, `feedback_pg.py` + migration | cần Docker/Postgres local |
| 8 | lifespan, semaphore, timeout, `/health`, `/ready` | test 503/504 bằng fake chậm |
| 9 | Frontend: `lib/api.ts`, thay mock | chạy tay đầu-cuối |
| 10 | Load test nhỏ (50 request song song) | đọc p95, tỉ lệ lỗi |

Sau mỗi thay đổi chung chạy `python -m pytest -q`, rồi `python examples/integration_demo.py`.

## 11. Việc frontend cần chỉnh theo plan này

- Tạo `lib/api.ts`: `fetch` có `credentials: 'include'`, bóc envelope lỗi, hiển thị theo bảng mã ở mục 5.5.
- Đổi `form.food_tags` thành `form.food` / `form.cuisine`.
- `MockDish` → `DishResult` (mục 5.1); xử lý `image_url`, `review_count` bằng `null`.
- Giữ danh sách `excludedIds` và `lastState` trong `GlobalFilterContext`; gửi `exclude_restaurant_ids` và `previous_results` mỗi lượt.
- `Trending`, `Featured`, `Mood`, `Spin` tạm giữ mock cho đến khi backend có nguồn dữ liệu (mục 4 "sau").
- Thêm trạng thái loading (AI có thể mất 1–2 giây), `409` retry một lần, `503`/`504` có nút "Thử lại".

## 12. Câu hỏi còn mở

- Nguồn `image_url`, `rating`, `review_count`, "trending": thêm cột vào DB, bảng riêng, hay giữ dữ liệu tĩnh ở frontend?
- Khi nào làm đăng nhập (`users`, đổi `anon_id` → `user_id`)?
- `mood` → `form` mapping do backend hay frontend sở hữu? (Cần team thống nhất trước khi code.)
- Ai sở hữu `src/backend/`? AGENTS.md chưa liệt kê; cần chốt trong PR.
