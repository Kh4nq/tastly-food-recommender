# Agent.md — Đăng ký / Đăng nhập / Đăng xuất (backend, frontend, database)

Tài liệu thiết kế cho tính năng tài khoản của Tastly. Đọc cùng
[BACKEND_PLAN.md](BACKEND_PLAN.md) và [AGENTS.md](../../AGENTS.md) ở gốc repo.
Tính năng đã code xong (bước 1–9 của §9). Việc còn lại nằm ở §12, dọn dẹp ở §13.
Cập nhật lần cuối: 2026-10-15.

### Mục tiêu

- Viết code lên màn hình kèm comment tiếng anh ngắn gọn
- Code phải clean và abstract
- Phải có giải thích chi tiết về code

## 0. Mục tiêu và phạm vi

| Trong phạm vi v1                                           | Ngoài phạm vi (làm sau)                              |
| ---------------------------------------------------------- | ---------------------------------------------------- |
| Đăng ký, đăng nhập, đăng xuất, `GET /me`                   | Quên mật khẩu qua email, xác minh email              |
| Đổi mật khẩu, sửa thông tin cá nhân (trang settings)       | Đăng nhập Google/Facebook (OAuth)                    |
| Hai vai trò `customer` / `business` (lưu nhãn)             | Chủ quán quản lý quán (cần bảng `restaurant_owners`) |
| Chạy đúng khi **nhiều người dùng đồng thời, nhiều worker** | Lưu lịch sử / sở thích theo tài khoản                |
| Tìm kiếm ẩn danh vẫn dùng được như cũ                      | 2FA, quản trị viên                                   |

Nguyên tắc: **đăng nhập là tùy chọn**. `/api/search` và chatbox phải tiếp tục chạy với
cookie `anon_id` mà không cần tài khoản.

## 1. Trạng thái hiện tại

Đã làm xong và có test (`tests/backend/test_auth_*.py`, `test_api_auth.py`):

- Đăng ký, đăng nhập, đăng xuất, `GET/PUT /me`, đổi mật khẩu.
- Phiên là token ngẫu nhiên, chỉ lưu hash trong `auth_sessions`; cookie `auth` HttpOnly.
- Chống lạm dụng: khoá tài khoản, rate limit theo IP, cổng băm mật khẩu, kiểm `Origin`.
- Frontend nối API; `/profile`, `/settings/*` chặn bằng `requireUser` (`lib/auth-server.ts`).

Phần còn lại: §12 (việc cần làm) và §13 (dọn dẹp). Các mục 2–8 là tài liệu thiết kế của
phần đã làm, giữ để tra cứu.

## 2. Quyết định kiến trúc

| Chủ đề              | Chọn                                                                                      | Lý do                                                 | Phương án khác                                                |
| ------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------- |
| Lưu tài khoản       | Bảng `users` trong Postgres hiện có                                                       | Đã có DB + pool, không thêm hạ tầng                   | Dịch vụ ngoài (Auth0/Supabase): thêm phụ thuộc                |
| Phiên đăng nhập     | **Token ngẫu nhiên + bảng `auth_sessions`**, cookie HttpOnly                              | Thu hồi được tức thì, mọi worker thấy cùng trạng thái | JWT: không thu hồi được, phải thêm blocklist                  |
| Băm mật khẩu        | `hashlib.scrypt` (stdlib)                                                                 | Không thêm dependency                                 | `argon2-cffi` (khuyến nghị OWASP, nhưng đổi dependency chung) |
| Cookie              | Tên `auth`, `HttpOnly`, `SameSite=Lax`, `Secure` theo `settings.cookie_secure`            | Giữ tên cũ để `Header.tsx` không vỡ                   |                                                               |
| Tách với session AI | `anon_id` giữ nguyên, `auth` là cookie riêng                                              | Search không phụ thuộc đăng nhập                      | Gộp một cookie: rủi ro làm hỏng luồng AI                      |
| Schema chung        | Schema auth nằm trong `backend/api/schemas.py`, **không** đưa vào `src/common/schemas.py` | `common` chỉ chứa hợp đồng AI 1/2/3                   |                                                               |

## 3. Database

Thêm file migration idempotent `database/auth.sql` (không sửa `schema.sql`, nơi chứa
bảng dữ liệu món ăn). Chạy bằng cùng cách đang chạy `schema.sql`.

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS users (
    user_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email              TEXT NOT NULL,
    password_hash      TEXT NOT NULL,            -- "scrypt$N$r$p$salt_hex$hash_hex"
    full_name          TEXT NOT NULL,
    phone              TEXT,
    role               TEXT NOT NULL,
    shop_name          TEXT,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_users_role CHECK (role IN ('customer', 'business')),
    CONSTRAINT chk_users_email_lower CHECK (email = lower(email)),
    CONSTRAINT chk_users_shop_name CHECK (role <> 'business' OR shop_name IS NOT NULL),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash   TEXT PRIMARY KEY,               -- SHA-256 hex của token trong cookie
    user_id      UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires ON auth_sessions (expires_at);

COMMIT;
```

Ghi chú thiết kế:

- **Email chuẩn hoá ở app** (`strip().lower()`), DB có `CHECK` làm lưới an toàn. Một
  `UNIQUE (email)` là đủ để cả đăng ký và đăng nhập dùng index.
- **Đăng ký chống race bằng ràng buộc UNIQUE**, không "SELECT rồi INSERT". Hai người
  cùng đăng ký một email thì một người nhận `UniqueViolation` → `409 email_taken`.
- **Chỉ lưu hash của token**. Lộ bảng `auth_sessions` thì kẻ tấn công không dùng được
  token. Token thô chỉ nằm ở cookie.
- `role` là `TEXT` + `CHECK` (không dùng ENUM) để thêm vai trò không cần `ALTER TYPE`.
- `failed_login_count` / `locked_until` nằm trong DB nên **mọi worker dùng chung** một
  bộ đếm, không phải bộ đếm trong RAM của từng process.
- Dọn session hết hạn: `DELETE FROM auth_sessions WHERE expires_at < now()`. Chạy bằng
  job định kỳ; trong lúc chưa có job thì xoá "lười" khi đăng nhập (xoá các dòng hết hạn
  của đúng user đó). Kiểm tra `expires_at > now()` luôn nằm trong câu truy vấn xác thực,
  nên session hết hạn chưa được dọn vẫn không dùng được.

## 4. Backend

### 4.1 Bố cục file (theo đúng kiến trúc ports/adapters hiện có)

```
backend/
  ports.py                 + UserStore, AuthSessionStore (Protocol), EmailTakenError
  adapters/user_pg.py      PostgresUserStore (psycopg, pool dùng chung)
  adapters/auth_session_pg.py
  adapters/auth_memory.py  bản in-memory cho test (giống session_memory.py)
  services/passwords.py    hash_password / verify_password (thuần, không I/O)
  services/auth_service.py register / login / logout / current_user / change_password
  api/routes_auth.py       controller mỏng: HTTP vào, HTTP ra
  api/schemas.py           + RegisterRequest, LoginRequest, UserOut ...
  api/deps.py              + CurrentUser, OptionalUser (đọc cookie auth)
  api/errors.py            + handler cho lỗi auth
  settings.py              + tham số auth (mục 4.6)
  wiring.py                + dựng store/service, thêm vào Services
```

`Services` (frozen dataclass trong `deps.py`) thêm field `auth_service`. Test truyền
bản in-memory như đang làm với `search_service`.

### 4.2 API

Mọi route dưới `/api/auth`. Lỗi dùng chung envelope hiện có
`{"error": {"code", "message", "request_id"}}`.

| Method + path                    | Body                                                  | Thành công                                        | Lỗi                                                           |
| -------------------------------- | ----------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------- |
| `POST /api/auth/register`        | `role, full_name, email, phone, password, shop_name?` | `201 {user}` + set cookie `auth` (đăng nhập luôn) | `422 validation_error`, `409 email_taken`, `429 rate_limited` |
| `POST /api/auth/login`           | `email, password`                                     | `200 {user}` + set cookie `auth`                  | `401 invalid_credentials`, `429 rate_limited`                 |
| `POST /api/auth/logout`          | không                                                 | `204`, xoá dòng `auth_sessions`, xoá cookie       | luôn `204` (idempotent)                                       |
| `GET /api/auth/me`               | không                                                 | `200 {user}`                                      | `401 unauthenticated` (và xoá cookie hỏng)                    |
| `PUT /api/auth/me`               | `full_name, phone, shop_name?`                        | `200 {user}`                                      | `401`, `422`                                                  |
| `POST /api/auth/change-password` | `current_password, new_password`                      | `204`, thu hồi **mọi session khác**               | `401`, `403 wrong_password`, `422`                            |

`user` trả về: `{id, email, full_name, phone, role, shop_name}`. **Không bao giờ** trả
`password_hash`, `failed_login_count`, `locked_until`.

Thêm vào `errors.py` các mã: `email_taken` (409), `invalid_credentials` (401),
`unauthenticated` (401), `wrong_password` (403), `rate_limited` (429 kèm `Retry-After`).
Thông báo lỗi là chuỗi chung, **không** echo email/mật khẩu người dùng gửi lên.

### 4.3 Mật khẩu

- Định dạng lưu: `scrypt$<N>$<r>$<p>$<salt_hex>$<hash_hex>`. **Tham số nằm trong chuỗi
  hash**, nên sau này tăng độ khó chỉ cần băm lại khi người dùng đăng nhập thành công
  (`needs_rehash`), không phải chuyển dữ liệu hàng loạt.
- Tham số khởi điểm theo OWASP: `N=2**15, r=8, p=3` (~32 MiB mỗi lần băm). Phải truyền
  `maxmem` (ví dụ 64 MiB) vì giới hạn mặc định của OpenSSL có thể báo lỗi ở mức này.
  **Đo trên máy chạy thật** và chỉnh để một lần băm vào khoảng 100–250 ms.
- Lưu ý: ví dụ `n=2**14, p=1` trong câu trả lời trước chỉ để minh hoạ, **thấp hơn
  khuyến nghị**. Dùng tham số ở trên.
- So sánh bằng `hmac.compare_digest`. Salt 16 byte từ `os.urandom`.
- Độ dài mật khẩu: tối thiểu 8, **tối đa 128** (chặn kẻ gửi chuỗi khổng lồ để ăn CPU).
- Đăng nhập với email không tồn tại vẫn phải **băm một mật khẩu giả** để thời gian phản
  hồi không tiết lộ email nào có tài khoản.
- Không dùng `EmailStr` của Pydantic (cần thêm `email-validator`). Dùng
  `Field(pattern=...)` đơn giản và độ dài tối đa 254.

### 4.4 Phiên đăng nhập

1. Đăng nhập đúng → `token = secrets.token_urlsafe(32)`.
2. Lưu `sha256(token)` vào `auth_sessions` với `expires_at = now() + 7 ngày`.
3. Cookie `auth=<token>`: `HttpOnly`, `SameSite=Lax`, `Secure=settings.cookie_secure`,
   `Path=/`, `Max-Age=7 ngày`.
4. Mỗi request cần user: băm cookie, một truy vấn `JOIN`:
   `auth_sessions ⨝ users WHERE token_hash = %s AND expires_at > now()`.
   Không có dòng → coi như chưa đăng nhập.
5. Gia hạn trượt: chỉ `UPDATE last_seen_at/expires_at` khi `last_seen_at` cũ hơn 1 giờ,
   để không ghi DB trên mọi request.
6. Đăng nhập lại / đổi mật khẩu → phát token mới, không tái dùng token cũ (chống
   session fixation).
7. Đổi mật khẩu thành công → `DELETE FROM auth_sessions WHERE user_id = %s AND token_hash <> <hiện tại>`.

`deps.py` thêm hai dependency theo kiểu `Annotated` giống `SessionId`:

- `OptionalUser`: trả `User | None`, **không** lỗi. Dùng cho route chấp nhận cả khách.
- `CurrentUser`: ném `401 unauthenticated` nếu không có. Dùng cho `/me`, settings.

`/api/search` **không** gắn dependency nào trong hai cái này ở v1, để tìm kiếm không
tốn thêm truy vấn DB.

### 4.5 Chống lạm dụng

| Mối đe doạ                            | Biện pháp                                                                                                                                                   |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dò mật khẩu một tài khoản             | `failed_login_count` ≥ 5 → `locked_until = now() + 15 phút`; reset về 0 khi đăng nhập đúng. Cập nhật bằng **một câu `UPDATE` nguyên tử**, không đọc-rồi-ghi |
| Dò nhiều tài khoản từ một nguồn       | Token bucket theo IP trong RAM cho `/login` và `/register` (xấp xỉ khi nhiều worker; đủ dùng v1)                                                            |
| Kẻ xấu cố ý khoá tài khoản người khác | Chấp nhận rủi ro ở v1 vì thời gian khoá ngắn; nếu thành vấn đề thì chuyển sang khoá theo cặp (email, IP)                                                    |
| Liệt kê email                         | `/login` luôn trả cùng một lỗi `invalid_credentials` + băm giả. `/register` buộc phải báo `email_taken`; chấp nhận                                          |
| CSRF                                  | `SameSite=Lax` + chỉ đổi trạng thái bằng `POST/PUT`, không dùng `GET`; kiểm tra thêm header `Origin` ở các route POST auth nếu có                           |
| Lộ cookie qua XSS                     | `HttpOnly`; frontend **không** lưu token/user vào `localStorage`                                                                                            |
| Mật khẩu lọt vào log                  | Không log body của `/api/auth/*`. Log chỉ có `request_id`, mã lỗi                                                                                           |
| Chống đoán mã                         | `token_urlsafe(32)` ~256 bit; so khớp qua hash trong DB                                                                                                     |

**IP thật khi đi qua Next rewrite** (đã đo trên Next 16.3.6): Next **không**
thêm IP khách vào `X-Forwarded-For`, và giữ nguyên header do khách tự gửi. Hệ quả:

- Backend chỉ thấy IP của Next (`127.0.0.1`) cho mọi khách, nên giới hạn theo IP thực
  chất là giới hạn **toàn site**, một bucket chung.
- `BACKEND_TRUST_PROXY=true` khi chỉ có Next là **không an toàn**: kẻ tấn công tự điền
  `X-Forwarded-For` giả để né giới hạn. Chỉ bật khi có reverse proxy đứng trước Next
  _thêm_ IP thật vào header, và cổng của Next/backend không truy cập trực tiếp được.
- **Quyết định v1 (đồ án/demo): giữ `trust_proxy=false`, nới giới hạn** (30 lần dồn,
  60 lần/phút) để nó chỉ là van chống ngập chứ không khoá được người dùng thật. Bảo vệ
  thật nằm ở khoá theo tài khoản, cổng băm và kiểm `Origin`, đều không phụ thuộc IP.
- Khi triển khai thật có reverse proxy: bật `trust_proxy`, hạ lại giới hạn (ví dụ 10/10)
  để thành giới hạn theo từng khách.

Origin của trình duyệt đi qua Next nguyên vẹn, nên guard `Origin` hoạt động bình thường.

### 4.6 Cấu hình (`settings.py`, đọc từ env, có `_number`/`_flag` sẵn)

| Biến                                | Mặc định | Ý nghĩa                                           |
| ----------------------------------- | -------- | ------------------------------------------------- |
| `BACKEND_AUTH_SESSION_DAYS`         | 7        | Thời gian sống của phiên                          |
| `BACKEND_AUTH_HASH_CONCURRENCY`     | 4        | Số lần băm mật khẩu chạy song song mỗi process    |
| `BACKEND_AUTH_MAX_FAILURES`         | 5        | Số lần sai trước khi khoá                         |
| `BACKEND_AUTH_LOCK_MINUTES`         | 15       | Thời gian khoá                                    |
| `BACKEND_AUTH_HASH_QUEUE_TIMEOUT_S` | 2        | Chờ slot băm tối đa bao lâu trước khi `503`       |
| `BACKEND_AUTH_RATE_BURST`           | 30       | Số lần thử liên tiếp của một IP (bước 7, xem 4.5) |
| `BACKEND_AUTH_RATE_PER_MINUTE`      | 60       | Số lần thử bền vững mỗi phút của một IP           |
| `BACKEND_TRUST_PROXY`               | false    | Đọc `X-Forwarded-For` (chỉ khi sau proxy tin cậy) |

Không có bí mật mới nào cần thiết (token ngẫu nhiên, không có khoá ký). Cập nhật
`.env.example` nếu thêm biến; không commit `.env`.

## 5. Chịu tải nhiều người dùng

| Vấn đề                                                              | Cách xử lý                                                                                                                                                         |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Băm mật khẩu tốn CPU/RAM, một đợt đăng nhập dồn dập làm treo server | `run_in_threadpool` + **`asyncio.Semaphore(hash_concurrency)` đặt trước** khi vào threadpool; không có slot sau ~2 s → `503 busy` (đã có handler và `Retry-After`) |
| Không dùng chung `Gate` của AI                                      | `Gate` chạy trên _default executor_ và giữ thread khi chờ semaphore. Hàng chờ AI đầy sẽ làm login chờ theo. Dùng semaphore asyncio riêng như dòng trên             |
| Bộ nhớ khi băm                                                      | Mỗi lần ~32 MiB × `hash_concurrency` × số worker. Tính tổng trước khi tăng worker                                                                                  |
| Nhiều worker                                                        | Không có trạng thái trong RAM quan trọng: phiên, bộ đếm sai, khoá đều ở Postgres                                                                                   |
| Hết kết nối DB                                                      | Mỗi lần xác thực là 1 truy vấn ngắn. Giữ `workers × pool.max_size < max_connections`. Chỉ route cần user mới gọi `CurrentUser`                                     |
| Hai tab cùng đăng ký / đăng nhập                                    | Ràng buộc `UNIQUE` và `UPDATE` nguyên tử quyết định; không cần khoá ở tầng app                                                                                     |
| `Header` render mỗi trang                                           | Chỉ kiểm tra `has("auth")` để hiện icon (rẻ). Xác thực thật ở các trang cần đăng nhập (mục 6)                                                                      |
| Bảng `auth_sessions` phình                                          | Index `expires_at` + job dọn; truy vấn xác thực đã lọc `expires_at > now()`                                                                                        |
| DB lỗi                                                              | `/search` vẫn chạy (không phụ thuộc auth). Route auth trả `503`/`500` theo envelope hiện có                                                                        |

Số worker ban đầu giữ 1–2 như BACKEND_PLAN §7. Nếu muốn tăng, đo p95 của `/login` dưới
tải trước (xem mục 9).

## 6. Frontend

### 6.1 Quy tắc

- Hiển thị lỗi theo `ApiError.code`, tra bảng i18n; **không** in `message` thô của server.
- Thuộc tính input: `autoComplete="email"`, `"current-password"`, `"new-password"`,
  `minLength={8}`, `maxLength={128}`, để trình quản lý mật khẩu hoạt động.
- Tham số `?next=` chỉ chấp nhận đường dẫn tương đối bắt đầu bằng `/` và **không** bắt
  đầu bằng `//` (chống open redirect).
- **Trang cần đăng nhập** (`/profile`, `/settings/*`): server component gọi
  `${BACKEND_URL}/api/auth/me` với `headers: { cookie: (await cookies()).toString() }`
  và `cache: "no-store"`. `401` → `redirect("/login?next=...")`. Đây mới là chỗ chặn
  thật; `Header` chỉ làm giao diện.
- Cookie `auth` cũ (`auth=1`) còn trong trình duyệt: server component **không** đặt/xoá
  được cookie, nên `Set-Cookie` xoá cookie hỏng mà `/me` trả về không tới trình duyệt.
  Người đó bị chuyển sang `/login`, nhưng `Header` vẫn hiện icon "đã đăng nhập" cho tới
  khi họ đăng nhập (ghi đè cookie) hoặc bấm đăng xuất. Chỉ là hiển thị, không lộ dữ liệu.
- Chatbox và tìm kiếm của khách không đổi.

## 7. Bảo mật: checklist

Đã xác nhận trong code (2026-10-15):

- [x] `UserOut` không chứa mật khẩu, hash, bộ đếm; route/service auth không ghi log body.
- [x] Cookie `auth`: `HttpOnly`, `SameSite=Lax`, `Secure` theo `settings.cookie_secure`.
- [x] Token chỉ lưu dạng hash SHA-256 trong DB.
- [x] Đăng nhập email không tồn tại vẫn băm mật khẩu giả (`passwords._dummy_hash`).
- [x] Giới hạn độ dài mật khẩu; `role` chỉ nhận `customer`/`business` và đọc từ DB.
- [x] Đổi mật khẩu thu hồi session cũ rồi cấp token mới cho phiên hiện tại.
- [x] Rate limit, khoá tạm, cổng băm, kiểm `Origin` có test (`test_auth_limits.py`).
- [x] Session hết hạn được dọn khi đăng nhập (`AuthService._sweep_expired`, tối đa mỗi `cleanup_every` = 1 giờ, có test).

Còn lại (chi tiết ở §12, nhóm C):

- [ ] HTTPS ở môi trường thật và `BACKEND_COOKIE_SECURE=true`.

## 8. Kiểm thử

Không gọi mạng, không cần API key (theo AGENTS.md). Test auth nằm trong `tests/backend/`
(`test_auth_*.py`, `test_api_auth.py`), dùng `create_app(services=...)` với `auth_memory`.
Adapter `*_pg` cần Postgres thật (Docker). Sau thay đổi chung:
`python -m pytest -q`, rồi `python examples/integration_demo.py`.

## 9. Thứ tự làm

Bước 1–9 đã xong. Còn lại:

| #   | Việc                                                              | Kiểm tra                              |
| --- | ----------------------------------------------------------------- | ------------------------------------- |
| 10  | Đo tải `/login` bằng `scripts/load_login.py`, rà checklist §7     | p95, tỉ lệ 401/429/503 ghi vào §12    |

## 10. Quy tắc cho agent làm trong thư mục này

- Auth là phần của backend. **Không** sửa `src/common/schemas.py`, `src/retrieval/`,
  `src/conversation/`, `src/ranking/`.
- Thêm migration, route, biến môi trường, dependency: **báo owner** trong PR.
  `src/backend/` chưa có owner ghi trong AGENTS.md; cần chốt trong PR đầu tiên.
- Không thêm dependency mới nếu stdlib làm được. Muốn chuyển sang `argon2-cffi` thì đó
  là thay đổi dependency chung, cần review.
- Không commit `.env`, không đưa mật khẩu/khoá thật vào test hay tài liệu.
- Mật khẩu và email người dùng không xuất hiện trong log ở bất kỳ mức nào.
- Khi chưa làm xong một phần, entry point của nó phải ném `NotImplementedError` rõ ràng,
  không trả dữ liệu giả ở code production.

## 11. Câu hỏi còn mở

- Vai trò `business` cần làm gì ở v1? Hiện chỉ là nhãn. Nếu muốn chủ quán quản lý quán
  thì cần bảng `restaurant_owners(user_id, food_place_id)` và quy trình xác minh.
- Có cần xác minh email / quên mật khẩu không? Cần dịch vụ gửi mail (phụ thuộc ngoài).
- Khi đã đăng nhập, có gắn `user_id` vào AI và lưu sở thích theo tài khoản không?
  (BACKEND_PLAN §12). Nếu có, `anon_id` hiện tại cần chiến lược gộp vào tài khoản.
- Triển khai thật chạy sau reverse proxy nào? Quyết định cách đọc IP khách (mục 4.5).
- Có muốn chuyển sang đăng nhập Google để khỏi giữ mật khẩu không? Bảng `users` vẫn cần.

## 12. Việc còn lại

Cập nhật 2026-10-15. Xếp theo mức ưu tiên trong từng nhóm.

### Nhóm A — Tính năng và giao diện

| #   | Việc                                                                                                                                                                                                                                                               | File                                                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| A4  | Bán kính tìm kiếm mặc định: luồng mới không đặt `max_distance_km` nên `map_places` và top 12 có thể ở xa. Chốt với owner frontend có mặc định 5 km không (máy cá nhân đã thử đặt trong `emptyPreferences`), rồi commit hoặc bỏ                                       | `lib/conversation-state.ts`                              |
| A5  | Bản đồ Leaflet (khi không có token) vẽ **mọi** quán khớp thành pin đầy đủ nên nặng và rối. Pin lớn chỉ cho quán `priority`, còn lại `CircleMarker` + `preferCanvas`; căn khung theo quán xếp hạng và vị trí người dùng                                              | `components/search/MapView.tsx`                          |
| A6  | `scrollWheelZoom` đã bị đổi lại `true` ở commit của bạn bạn. Quyết định giữ hay tắt                                                                                                                                                                                | `components/search/MapView.tsx`, `MapboxView.tsx`        |
| A7  | Form thông tin quán (`business`) chưa nối backend (`profile.savedAlert` còn ghi "chưa nối backend thật"). Phụ thuộc quyết định §11 về `restaurant_owners`                                                                                                           | `components/profile/RestaurantInfoForm.tsx`, `locales/vi.ts` |

### Nhóm B — Kiểm tra trước khi tin

| #   | Việc                                                                                                                                                                       |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B2  | Kiểm tay đầu–cuối luồng tài khoản (đăng ký, đăng nhập, đăng xuất, đổi mật khẩu, vào `/profile` khi chưa đăng nhập) vì bạn bạn đã viết lại `/search`, layout và provider     |
| B3  | Bước 10: đo `/login` bằng `scripts/load_login.py` (cách bật backend ghi ở đầu file script), ghi p95 và tỉ lệ 401/429/503 vào đây                                            |
| B4  | Ép lỗi để xem `app/error.tsx` và `app/global-error.tsx` hiển thị đúng (tắt backend rồi tải `/` khi đã đăng nhập; chỉ `not-found.tsx` đã được xem thử) |

### Nhóm C — Trước khi triển khai thật

| #   | Việc                                                                                                                                                                             |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C1  | HTTPS và `BACKEND_COOKIE_SECURE=true`; thêm domain thật vào `cors_origins` (hiện chỉ `localhost`, `127.0.0.1`)                                                                   |
| C3  | Có reverse proxy thì mới bật `BACKEND_TRUST_PROXY=true` (proxy phải thêm IP thật vào cuối `X-Forwarded-For`), rồi hạ rate limit về khoảng 10/10 (xem §4.5)                         |
| C4  | Token Mapbox `pk.` bị nhúng vào JS gửi trình duyệt: đặt giới hạn URL và cảnh báo chi phí trên tài khoản Mapbox                                                                   |
| C5  | Biến môi trường frontend đã ghi ở `src/frontend/README.md`. Còn thiếu: thêm `NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN` và `NEXT_PUBLIC_WEB3FORMS_ACCESS_KEY` vào `.env.example` ở gốc repo (file dùng chung, cần báo owner) |

Giới hạn đã chấp nhận (có comment `ponytail:` trong code): bộ đếm rate limit nằm trong RAM
từng worker; người dùng chung NAT dùng chung một bucket; chưa khoá theo cặp (email, IP).
Nâng cấp khi thành vấn đề thật: Redis hoặc bảng Postgres cho bộ đếm.

### Nhóm D — Cần quyết định

Xem §11. Thêm: bán kính mặc định (A4) và việc có làm quản lý quán cho `business` (A7).

## 13. Dọn dẹp

Chưa làm gì ở các mục dưới. Mỗi mục: kiểm tra trước, rồi mới xoá.

### Repo

| #   | Mục                                                                                                                                                                         | Cách xử lý                                                                                     |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| R2  | `dist/` nằm trong `.gitignore` nhưng 6 file `dist/kaggle/*.py` vẫn bị theo dõi (do bạn bạn thêm bằng `add -f`). **Không tự gỡ**: `git rm --cached` sẽ xoá các file đó khỏi máy bạn ấy khi họ pull | Hỏi bạn bạn còn dùng không: còn thì chuyển sang `scripts/`, không thì `git rm -r dist` |
| R3  | `material/`: 4 ghi chú học tập đã commit và 1 file chưa commit (`auth_chong_lam_dung_va_frontend_kien_thuc.md`)                                                             | Chọn commit chung hay giữ cá nhân (thêm vào `.gitignore`)                                      |
| R4  | `stash@{0}` "WIP on fullstack: b7abbd5" (8 file backend, ~1400 dòng, auth đang làm dở). Thử `git apply --check --reverse` thấy HEAD đã thay đổi nhiều sau đó nên **chưa chứng minh được** nó đã nằm trong HEAD | Nếu chắc đã commit xong auth: `git stash drop`. Sợ mất: `git branch backup-stash stash@{0}` trước |
| R5  | Nhánh local `backup-fullstack-fc99f9e` (bản `fullstack` trước khi viết lại lịch sử)                                                                                         | Giữ tới khi bạn bạn xác nhận `fullstack` mới ổn, rồi `git branch -D`                           |
| R7  | Nhánh local chưa merge vào `fullstack`: `HBK`, `backup-hbk`, `backend`, `merge-frontend` (ahead 1). Nhánh remote cũ: `backup/full-integration-20261007`, `fullstack-dat`, `fix/fullstack-setup-test`, `chore/repo-cleanup-setup`, `merge-frontend` | Chạy `git branch -r --no-merged origin/fullstack`, xoá những nhánh không còn dùng (hỏi chủ nhánh) |

### Tài liệu

| #   | Mục                                                                                                                                       | Cách xử lý                                                                 |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| D1  | `src/frontend/FRONTEND_PLAN.md` trỏ tới `PLAN.md` ở gốc repo, file đó **không tồn tại**                                                   | Sửa link hoặc bỏ                                                           |
| D2  | `BACKEND_PLAN.md`, `FRONTEND_PLAN.md` mô tả kế hoạch ban đầu (tìm kiếm ẩn danh, `anon_id`), chưa phản ánh tài khoản và luồng tìm kiếm mới | Cập nhật hoặc ghi rõ đầu file là "lịch sử"                                 |

### Code

| #   | Mục                                                                                                                                  | Cách xử lý                                                              |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| K1  | Sau khi bạn bạn viết lại `/search`, có thể còn component, hàm, khoá i18n không ai import (ví dụ trong `components/search`, `lib/`)    | Tìm bằng `grep` hoặc `npx knip`, xoá sau khi `tsc`/`eslint` sạch        |
| K2  | `locales/vi.ts`: khoá `profile.savedAlert` còn ghi "chưa nối backend thật"                                                           | Gỡ khi A7 xong                                                          |
