# AI 2 MVP — báo cáo bàn giao

## Patch: extensible structured hard constraints

- BEFORE patch: **254 passed, 0 failed**.
- AFTER patch: **301 total, 301 passed, 0 failed**; toàn bộ tests cũ giữ nguyên.
- Full suite: `.\.venv\Scripts\python.exe -m pytest -q`.
- Conversion demo đã chạy thành công; không gọi API thật.
- Modified: `src/conversation/providers/structured.py`,
  `src/conversation/providers/mock.py`, `src/conversation/prompts.py`,
  `README.md`, `AI2_MVP_REPORT.md`.
- Created: `tests/test_extensible_constraints.py`.
- Không sửa public schema, rule parser, router hay state manager.
- Cả hai adapter tiếp tục gọi `.to_update()`, nay delegate cho converter chung
  `llm_output_to_preference_update`; không nhân đôi domain logic theo provider.
- Policy: key `strip().lower()`, không dịch semantic; duplicate sau normalize
  **last value wins**; reserved/state keys và key rỗng **reject validation**.
  Value hỗ trợ str/int/float/bool/list[str], reject nested object/null/nonfinite.
  Prompt giữ mong muốn mềm ở soft preferences, không tự nâng thành hard.
- Dictionary wire cũ vẫn đọc được để tương thích; JSON Schema gửi LLM và
  serialization mới chỉ dùng list entries. Public add_hard_constraints vẫn dict.

Conversion demo (lược bỏ các field mặc định):

```json
{
  "Structured LLM Output": {
    "set_values": {"food": ["ramen"]},
    "add_hard_constraints": [
      {"key": "budget_max", "value": 150000},
      {"key": "parking", "value": true},
      {"key": "allergen_free", "value": "peanut"}
    ]
  },
  "PreferenceUpdate": {
    "set_values": {"food": ["ramen"]},
    "add_hard_constraints": {
      "budget_max": 150000, "parking": true, "allergen_free": "peanut"
    }
  },
  "UserPreferenceState": {
    "session_id": "S001", "food": ["ramen"],
    "hard_constraints": {
      "budget_max": 150000, "parking": true, "allergen_free": "peanut"
    }
  }
}
```

Các số liệu bên dưới là baseline/bàn giao MVP trước patch này.

## BASELINE

- Đã inspect pyproject, toàn bộ common/conversation foundation, tests và dataset trước chỉnh sửa.
- Python 3.11.7; Pydantic v2.
- **87 tests, 87 passed, 0 failed**; dataset 48 cases.

## AFTER

- Full suite: **254 tests, 254 passed, 0 failed**.
- Giữ toàn bộ 48 regression cases ban đầu và các assertions foundation.
- Dataset hiện có **96 cases**. Harness được mở rộng để truyền previous results,
  mock fixtures và kiểm tra riêng rule update khi case cần reference/hybrid.
- Demo offline chạy thành công; sáu trace gồm ba demo bắt buộc và bốn ví dụ A–D
  (demo feedback đồng thời là D).
- **0 external API calls trong tests/demo**. Unit tests chặn network.
- Public contract giữ tên/field cũ; chỉ thêm PreviousResult và optional
  UserRequest.previous_results. State manager foundation không cần sửa.

Lệnh kiểm chứng:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m conversation.demo --output examples/ai2_mvp_traces.json
```

## FILES CREATED

```text
.env.example
AI2_MVP_REPORT.md
examples/ai2_mvp_traces.json
src/conversation/models.py
src/conversation/config.py
src/conversation/reference_resolver.py
src/conversation/prompts.py
src/conversation/service.py
src/conversation/conversation_logger.py
src/conversation/providers/__init__.py
src/conversation/providers/base.py
src/conversation/providers/mock.py
src/conversation/providers/structured.py
src/conversation/providers/openai_provider.py
src/conversation/providers/gemini_provider.py
tests/conftest.py
tests/test_conversation_mvp.py
tests/test_providers.py
```

## FILES MODIFIED

```text
.gitignore
pyproject.toml
README.md
src/common/schemas.py
src/conversation/__init__.py
src/conversation/rule_parser.py
src/conversation/parser.py
src/conversation/demo.py
tests/test_conversation.py
tests/data/conversation_cases.json
```

## ARCHITECTURE

- Rule-only: UserRequest → detailed rules → form merge → PreferenceUpdate →
  state manager → UserPreferenceState → optional log. Không khởi tạo provider.
- Hybrid: rules còn unresolved text → một structured provider call → validate →
  merge với rule/form → update state → log. LLM không nhắc field rule không làm
  mất field đó; explicit form thắng, removal thắng addition cùng NLP update.
- Feedback: previous_results + message + current_state → resolver map ordinal/name
  sang ID thật; LLM phân tích sentiment/similar-to trong cùng một call → code
  kiểm chứng reference → lưu references và relative directions, không ranking.
- Reference đơn lẻ resolve chắc chắn không cần LLM. Reference thiếu/mâu thuẫn
  context giữ unresolved và clarification_required, không bịa ID.

## PROVIDERS

| Provider | Hoạt động | Kiểm chứng |
|---|---|---|
| Mock | Mapping/callback deterministic, instance call_count | Routing, feedback, errors, immutability |
| OpenAI | Official SDK lazy import, Responses structured parse, max_retries=0 | Fake SDK success/invalid/empty/timeout, one invocation |
| Gemini | Official SDK lazy import, JSON Schema, attempts=1, automatic function calling disabled | Fake SDK success/invalid/empty/timeout, one invocation |

Model/key cấu hình qua environment. Không chọn model cố định. Real providers
dùng projection đóng của PreferenceUpdate để đáp ứng schema strict, sau đó
validate và chuyển về public PreferenceUpdate. Chi tiết và nguồn tài liệu SDK
ở [README](README.md).

**Giới hạn: tối đa một external LLM API call mỗi message** với hai adapter tích
hợp. Không retry, repair call hoặc chuyển provider tự động. Mock không có call
external. Custom provider phải tuân thủ quy ước không tự retry.

LLM fail/thiếu config/thiếu SDK/invalid output → giữ rule/form, state vẫn được
cập nhật, parser_used=rule_fallback, partial_result=true và llm_error an toàn.
Logging fail không làm mất result. Latency ghi rule_parse_ms, llm_ms, total_ms.

## Bốn ví dụ thực tế

Các object dưới đây rút gọn field mặc định rỗng để dễ đọc.
Full UserRequest → RuleParseResult → LLM flag → PreferenceUpdate →
UserPreferenceState và metadata nằm trong
[trace JSON đã chạy](examples/ai2_mvp_traces.json).

### A. Tìm ramen dưới 150k trong 2km

```text
UserRequest: session_id=A, message="Tìm ramen dưới 150k trong 2km"
RuleParseResult:
  update.set_values.food=[ramen]
  update.add_hard_constraints={budget_max:150000,max_distance_km:2}
  requires_llm=false; unresolved_text=null
LLM called? NO
PreferenceUpdate:
  set_values.food=[ramen]
  add_hard_constraints={budget_max:150000,max_distance_km:2}
UserPreferenceState:
  food=[ramen]; hard_constraints={budget_max:150000,max_distance_km:2}
```

### B. Tìm ramen dưới 150k, quán đẹp nhưng đừng quá ồn

```text
UserRequest: session_id=B, message="Tìm ramen dưới 150k, quán đẹp nhưng đừng quá ồn"
RuleParseResult:
  update.set_values.food=[ramen]
  update.add_hard_constraints={budget_max:150000}
  update.add_semantic_preferences=[beautiful ambience]
  requires_llm=true; unresolved_text="nhưng đừng quá ồn"
LLM called? YES — MockProvider, đúng 1 lần; external=0
PreferenceUpdate:
  set_values.food=[ramen]; add_hard_constraints={budget_max:150000}
  add_semantic_preferences=[beautiful ambience,quiet]
UserPreferenceState:
  food=[ramen]; hard_constraints={budget_max:150000}
  semantic_preferences=[beautiful ambience,quiet]
```

### C. Không cần quán đẹp nữa

```text
UserRequest: session_id=C, message="Không cần quán đẹp nữa"
  current_state.semantic_preferences=[beautiful ambience]
RuleParseResult:
  update.remove_preferences=[beautiful ambience]
  update.add_semantic_preferences=[]
  requires_llm=false; unresolved_text=null
LLM called? NO
PreferenceUpdate: remove_preferences=[beautiful ambience]
UserPreferenceState: semantic_preferences=[]
```

### D. Cái thứ hai ổn nhưng hơi xa, tìm giống nó mà gần hơn

```text
UserRequest: session_id=D,
  message="Cái thứ hai ổn nhưng hơi xa, tìm giống nó mà gần hơn"
  previous_results=[{rank:1,restaurant_id:R001},{rank:2,restaurant_id:R002}]
RuleParseResult:
  update.relative_updates={distance:decrease}
  requires_llm=true
  unresolved_text="cái thứ hai ổn nhưng hơi xa giống nó mà"
LLM called? YES — MockProvider, đúng 1 lần; external=0
PreferenceUpdate:
  references=[{status:resolved,rank:2,restaurant_id:R002,
               mention:"cái thứ hai",sentiment:positive,similar_to:R002}]
  relative_updates={distance:decrease}
UserPreferenceState:
  reference_restaurants=[{status:resolved,rank:2,restaurant_id:R002,
                         mention:"cái thứ hai",sentiment:positive,similar_to:R002}]
  context.relative_updates={distance:decrease}
  hard_constraints={}  # Không tự đặt khoảng cách tuyệt đối
```

## KNOWN LIMITATIONS

- Rule coverage nhỏ, conservative; chưa hiểu toàn bộ tiếng Việt. Confidence chưa
  được hiệu chỉnh nên để None. Partial fallback có thể thiếu semantic/feedback.
- Mock thể hiện predetermined meaning, không chứng minh độ chính xác model thật.
  Chưa gọi API thật/benchmark; adapter tests kiểm tra ranh giới SDK bằng fake.
- Wire hard constraints đã được patch thành list key/value mở rộng; public vẫn
  là dict. Không cần sửa schema khi thêm feature. Xem policy conversion trong README.
- Reference dựa trên exact name/ordinal và caller context; không fuzzy matching,
  chưa có selected-result context để tự resolve “quán này”.
- JSONL local chưa rotation/đảm bảo ghi đồng thời đa process. total_ms đo đến
  khi có state, trước ghi log; không phải benchmark production.

Hoàn thành phạm vi AI 2 MVP và dừng để review.
