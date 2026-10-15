# AI2 safety patches sau benchmark — 2026-10-15

V3 vẫn là default, V4 opt-in; LOCAL_SLM_ENABLED mặc định false và OpenRouter
disabled. Đã triển khai các patch AI2 được duyệt, không sửa adapters, shared schema,
approved gold, labels, frontend/backend orchestration, AI1/AI3/database. Không
train/download, git pull/merge/commit/push, cleanup hoặc gọi API thật.

Baseline và handoff trước vẫn nguyên vẹn. Báo cáo mới nằm trong
`logs/ai2-safety-patch-20261015/final/`; các snapshot/attempt sơ bộ ở thư mục cha
và verified/ không được dùng làm kết quả cuối. Các full-generation V3 attempts
trước final đều incomplete; không dùng làm accuracy/latency hoặc fallback input.

## 1. Patch và root cause

| Vấn đề | Root cause / thay đổi | Giới hạn |
| --- | --- | --- |
| Hạt điều → peanut | Alias thiếu cashew; general allergy guard chỉ cần exclusions không rỗng. Mapping `hạt điều`, `cashew(s)`, `cashew nuts` → `cashew`; kiểm tra targets thực sự có trong positive allergy clause; không tự đổi target lạ thành một allergen đã biết | `allergens_excluded` hiện là list chuỗi extensible: không đổi shared schema. Literal extensible target chỉ được giữ nguyên khi có bằng chứng đúng target, không đoán synonym |
| Dị ứng đã xác nhận | Rejection giữ rule delta và state cũ; lỗi allergy evidence đặt clarification khi fallback không giải quyết được. Fallback có bằng chứng hợp lệ có thể clear rejection | State Manager giữ union/removal semantics; không viết policy xóa từng allergen hoặc đổi removal-wins contract |
| Lẩu/phở chay | Rule cũ chỉ nhận `ăn chay`, `món chay`. Nhận bounded positive dish phrases (lẩu/phở/bún/cơm/mì, nấm, thuần chay), đặt vegetarian=true và giữ tên món đầy đủ | Phủ định, điều kiện/alternative, tên quán/quoted names không tạo dietary commitment. Ambiguous phrasing vẫn cần inference/review |
| References | Missing mention bị biến thành generic unresolved rồi merge trùng. Ground mention theo ordinal gốc kể cả rank không có; deduplicate unresolved cùng mention. Selector rank/ID phải nhất quán với ordinal trong mention | IDs/ranks chỉ từ caller results. Không quyết định antecedent cho pronoun hoặc selection→sentiment policy |
| Food/context hallucination | Schema validity không chứng minh evidence. Bounded known-allergy-only turn không sinh food; temporal correction chỉ giữ meal_time; context.sentiment cần cue. Reference-only selection không sinh attributes/removals/relative events | Có đối chứng explicit food cạnh allergy, explicit Wi-Fi cạnh selector và open context. Guard không phải semantic verifier cho mọi free-text/context key |
| Nested JSON | RecursionError ngoài controlled validation boundary | OpenRouter outer/content JSON và Gemini validation trả ProviderError(code=invalid_output); usage/cost đã đọc giữ nguyên. Benchmark wire taps cũng catch nesting error; mocks only |

Allergy substitutions bị reject toàn delta provider, không âm thầm relabel hay
thay một allergen bằng allergen khác. Rule cashew là bằng chứng từ lời người dùng.
Một rejection có thể giữ được constraint đúng nhưng vẫn yêu cầu clarification;
đây là hành vi thận trọng. Unverified target không có canonical mapping không
được đổi thành peanut; clarification/fallback giữ các exclusions đã xác nhận.

## 2. Before/after — diagnostic, không phải independent benchmark

Frozen suite SHA256:
`db7c3b5d2c34800f66db5e6bfc797d59dabee05b44bf31ae7211e0d4c6b8ca63`.
Giữ 21 scored diagnostics + 4 unscored human-review candidates. Independent
adjudicated gold vẫn **0**. Không đọc sealed benchmark 105. Các regression mới
trong safety tests không được thêm vào accuracy denominator.

Guard-only comparison: **cùng raw responses/SLM results cũ**, áp dụng current
rules/normalization/evidence/resolver. `before-after-guards.json` kiểm tra byte
equality raw output, suite hash, IDs/label_status và scope của source changes.
Current SLM input thay đổi ở ba unscored cases: vegetarian-hotpot, retention,
cashew. Vì vậy replay này đo guards; không đo khả năng sinh với prompt mới.

| Metric (21 scored, trừ JSON) | V3 trước | V3 guard replay | V4 trước | V4 guard replay |
| --- | ---: | ---: | ---: | ---: |
| Raw/canonical delta exact | 12/21 | 12/21 | 15/21 | 15/21 |
| Effective delta exact | 17/21 | 19/21 | 18/21 | 19/21 |
| Final state exact | 17/21 | 19/21 | 18/21 | 19/21 |
| Effective delta F1 | .9438 | .9767 | .9545 | .9767 |
| Final-state F1 | .9608 | .9800 | .9608 | .9800 |
| Raw JSON/schema valid | 25/25 | 25/25 | 25/25 | 25/25 |

Rule-only giữ 14/21 scored. Cashew/vegetarian không được tăng denominator hoặc
gán gold mới: reports lưu state/flags cho review. Replay cả hai models giữ
food=[lẩu chay], vegetarian=true; cashew raw peanut được reject, final excludes
cashew, clarification=true, prior allergies preserved. Không tạo external calls.

Hai scored failures còn lại: ordinal-selection positive reference sentiment
(strict diagnostic expectation nhưng policy cần human signoff) và travel-English
thiếu motorbike context dù giữ 15 phút. Similar-reference pronoun vẫn unscored,
cần human review. Không sửa expected labels hoặc xóa các case này để tăng điểm.

Fresh-generation kiểm tra riêng ba inputs có rule context thay đổi. Không sinh
lại 21 scored inputs không đổi; guard-only replay là kết quả trước/sau chính.
Ba fresh cases giữ nguyên trạng thái unscored, không dùng để tính accuracy hoặc
chọn primary model. Không dùng interrupted full-generation attempts làm số liệu.

## 3. Chạy lại local

Chọn output chưa tồn tại; scripts từ chối ghi đè baseline. Hai local commands
phải chạy **lần lượt**, một Qwen model tại một thời điểm, cache-only NF4.

```powershell
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode replay --replay-report logs/ai2-freeze-20261015/v3.json --output logs/ai2-safety-patch-20261015/new-v3-replay.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode replay --replay-report logs/ai2-freeze-20261015/v4.json --output logs/ai2-safety-patch-20261015/new-v4-replay.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode local --run-local --adapter v3 --output logs/ai2-safety-patch-20261015/new-v3-local.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode local --run-local --adapter v4 --output logs/ai2-safety-patch-20261015/new-v4-local.json
.\.venv-fullstack\Scripts\python.exe scripts/compare_ai2_freeze.py --v3 logs/ai2-safety-patch-20261015/new-v3-local.json --v4 logs/ai2-safety-patch-20261015/new-v4-local.json --output logs/ai2-safety-patch-20261015/new-local-comparison.json
.\.venv-fullstack\Scripts\python.exe scripts/report_ai2_safety_patch.py --after-dir logs/ai2-safety-patch-20261015/final --output logs/ai2-safety-patch-20261015/new-before-after-guards.json
```

Runtime adapter selection vẫn dùng `LOCAL_SLM_ADAPTER_VERSION=v3|v4`, với explicit
LOCAL_SLM_ADAPTER_PATH ưu tiên. V3 path `models/ai2/ai2-qwen3-1.7b-lora-targeted-v3`,
V4 path `models/ai2/best_adapter_v4_experimental`. Không sửa defaults/env file.

Lệnh fresh subset đã dùng cho mỗi adapter (V3 xong mới chạy V4):

```powershell
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode local --run-local --adapter v3 --case-id vegetarian-hotpot --case-id vegetarian-hotpot-retention --case-id unknown-allergen-cashew --output logs/ai2-safety-patch-20261015/new-v3-changed-inputs.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_freeze.py --mode local --run-local --adapter v4 --case-id vegetarian-hotpot --case-id vegetarian-hotpot-retention --case-id unknown-allergen-cashew --output logs/ai2-safety-patch-20261015/new-v4-changed-inputs.json
```

`complete_suite=false` được ghi rõ cho subset. Provider fallback không nhận subset
như report đầy đủ; dùng final/v3-guard-replay.json hoặc final/v4-guard-replay.json
để pilot routing toàn suite trên raw outputs lịch sử. Chỉ dùng `*-local.json` trong
ví dụ fallback nếu người dùng đã chạy đủ 25 cases bằng các lệnh full ở trên.

## 4. Pilot providers — chỉ người dùng chạy live sau duyệt

Gemini dùng model ID thực sự từ config: `gemini-3.5-flash-lite`; CLI đọc lại
GEMINI_MODEL ở mỗi run. OpenRouter dùng `qwen/qwen3-32b` hoặc
`deepseek/deepseek-v3.2`. Cùng suite/schema/initial states, chọn sẵn ba case:
sesame, milk-peanut, unknown-allergen-cashew. Hai case đầu scored diagnostic;
cashew vẫn unscored candidate, chỉ review critical behavior, không tính accuracy.

PowerShell từ repo root, cấu hình chung cho cả ba providers:

```powershell
$ai2PilotArgs = @('--max-calls', '3', '--budget-usd', '0.33', '--reserve-usd', '0.10', '--max-tokens', '1024', '--case-id', 'sesame', '--case-id', 'milk-peanut', '--case-id', 'unknown-allergen-cashew')
```

Dry-run (không client/provider/API call, không cần key):

```powershell
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider gemini @ai2PilotArgs --output logs/ai2-pilot-user/gemini-dry.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider qwen32 @ai2PilotArgs --output logs/ai2-pilot-user/qwen32-dry.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider deepseek32 @ai2PilotArgs --output logs/ai2-pilot-user/deepseek32-dry.json
```

Mock: thêm `--mock`, dùng output khác (`*-mock.json`). Không cần API key.
Các lệnh live dưới đây **chưa được agent thực hiện**; chỉ chạy sau duyệt,
review reservation theo pricing/token cap và có key/credits:

```powershell
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider gemini --live --confirm-external-calls @ai2PilotArgs --output logs/ai2-pilot-user/gemini-live.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider qwen32 --live --confirm-external-calls @ai2PilotArgs --output logs/ai2-pilot-user/qwen32-live.json
.\.venv-fullstack\Scripts\python.exe scripts/benchmark_ai2_providers.py --provider deepseek32 --live --confirm-external-calls @ai2PilotArgs --output logs/ai2-pilot-user/deepseek32-live.json
```

Đây là **provider-independent mode**, không gọi full pipeline để quyết định
activation. Đánh giá pipeline fallback riêng bằng cùng lệnh, thêm
`--mode fallback --local-report logs/ai2-safety-patch-20261015/final/v3-guard-replay.json`
(hoặc v4-guard-replay.json), output mới `*-fallback-live.json`. Report phải đủ 25
cases và source/suite hashes phải trùng runtime; reports trước patch bị từ chối.
Đây là routing trên raw outputs lịch sử, khác fresh-generation. Nếu chạy lại full
local 25 cases, có thể thay --local-report bằng output mới đó. Cashew output cũ
bị reject sẽ gọi fallback; cả hai fresh subset outputs hiện trả cashew đúng và
không gọi fallback. Không coi lịch sử fallback rate là rate của fresh SLM.
Fallback chỉ gọi provider khi route
thực sự reject SLM; Rule/SLM accepted không gọi provider. Mỗi invocation cần
budget riêng; không tự chạy thêm fallback pilots ngoài allocation ban đầu.

Ba independent invocations có allocation tổng $.99, planned reservations <=$.90;
max 3 calls/provider, retry=0, timeout=30s, output cap=1024. Ledger reserve trước
dispatch, giữ reservation khi thiếu cost/failed request, dừng dispatch tiếp khi
không còn budget hoặc chạm call cap. Usage.cost cao hơn reserve chặn call sau;
một call đã billed không thể undo. Đây là estimated local admission limit,
không phải account spending cap: Gemini USD cost có thể unknown; actual spend
cần xem usage/billing. Thanh toán và account cap do người dùng kiểm soát.

Key chỉ từ environment. Có thể nhập vào PowerShell bằng secure prompt (sau duyệt):

```powershell
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenRouter API key' -AsSecureString)).Password
```

Chạy python trực tiếp như trên kế thừa environment của shell. `load_env()` dùng
setdefault: environment hiện có ưu tiên .env. Không truyền key qua CLI args,
không echo key, không bật OPENROUTER_ENABLED cho production; live opt-in chỉ tạo
benchmark provider instance. Test subprocess dùng sentinel giả qua inherited env,
assert Authorization nhận đúng key, transport bị mock và sockets offline; cố ý
echo sentinel trong mock wire để chứng minh report/stdout/stderr không lộ key.

## 5. Freeze gates và công việc còn lại

- Giữ V3 default. Guards tốt hơn không chứng minh V4 tốt hơn trên independent data.
- Cần human review selection sentiment và similar-reference antecedent; không
  chuyển các case chưa có policy thành gold/passing benchmark bằng đổi labels.
- English transport extraction còn thiếu; 15-minute bound không tự quy thành km.
- AI1 hiện không advertise allergens_excluded/max_travel_time_min trong supported
  hard keys. AI2 state đúng không chứng minh recommendation an toàn dị ứng/ETA;
  cần coordinated evidence/filter contract trước freeze toàn pipeline.
- Vegetarian hard_filter hiện hỗ trợ bool, nhưng catalog/returned candidate IDs,
  ranking và DB presentation vẫn cần trace thực để kết luận vụ phá lấu bò.
- Guards bounded không xác minh mọi câu điều kiện, tên quán, emotion scope hay
  context tự do. Target-scoped allergy retraction và semantic antecedents cần
  policy review; State Manager contract hiện tại được bảo toàn.
- Provider mocks không chứng minh availability/schema support/quota/cost thật.
  Live pilot và independent gold review là các gate kế tiếp, không fine-tune.

## 6. Files và validation evidence

Runtime AI2 đã sửa:

- `src/conversation/normalization.py`, `rule_parser.py`: cashew aliases/dietary rules.
- `src/conversation/evidence.py`, `parser.py`: grounding/validation/clarification.
- `src/conversation/reference_resolver.py`: mention/selector consistency/deduplication.
- `src/conversation/providers/openrouter_provider.py`, `gemini_provider.py`: controlled nesting errors.

Tools/tests/docs:

- `scripts/benchmark_ai2_providers.py`: controlled errors trong benchmark wire taps.
- `scripts/benchmark_ai2_freeze.py`: explicit case subset, đánh dấu incomplete suite; default vẫn 25 cases.
- `scripts/report_ai2_safety_patch.py`: paired immutable-output before/after report.
- `tests/test_ai2_freeze_findings.py`: bỏ strict xfail sau XPASS, assertions không đổi.
- `tests/test_ai2_safety_patch.py`: new counterexamples/contracts, không đổi benchmark gold.
- `docs/AI2_SAFETY_PATCH_HANDOFF_20261015.md`: handoff mới; handoff cũ không sửa.

Targeted final: **1.153 passed, 22 skipped, 0 xfailed**, XML/text reports trong
final/. Tám strict xfails gốc đều passing; 45 safety tests mới passing.
Policy cases còn lại là unscored/review hoặc frozen diagnostic failures, không
có xfail giả mới che đi kết quả. Integration demo offline passed; git diff --check
passed. Skips: 15 sealed readers, 7 thiếu optional OpenAI SDK; không yêu cầu cài SDK
để hoàn tất Gemini/OpenRouter tests. Full-suite bổ sung đã dừng ở review-artifact
tests vì chậm/resource contention, không có full-suite pass claim. Targeted runtime,
regression/provider contracts và actual Gemini SDK offline transport đều hoàn tất.

Repository đã dirty trước lượt này. `git diff` so với HEAD gồm cả incoming edits;
không coi toàn bộ diff là patch lượt này. Danh sách trên là scope edits lượt này,
và source checksum comparison kiểm tra chỉ bảy AI2 runtime files thay đổi từ
frozen benchmark, không có shared schemas/config/State Manager/AI1/AI3/backend edits.

## 7. Evidence cuối

- `final/before-after-guards.json`: 25 paired frozen raw outputs, effective 19/21
  cho mỗi adapter, raw equality và thay đổi SLM input được ghi riêng.
- `final/v3-changed-inputs.json`, `v4-changed-inputs.json`: fresh NF4 inference,
  chỉ 3 candidates, 3/3 JSON/schema valid mỗi adapter, scored=0. Cùng source,
  decoding, initial state/results/input được assert trong
  `candidate-pair-verification.json`. Full comparison tool giữ guard incomplete
  và từ chối subset; không nới guard để tạo bảng accuracy giả.
- Raw của cả hai: lẩu chay mới có food=[lẩu chay]/vegetarian=true; retention raw
  không thêm vegetarian nhưng state cũ và Rule giữ vegetarian=true; cashew raw
  hiện exclude cashew. Effective states đúng theo approved safety policy tests;
  không có SLM fallback/clarification ở ba fresh cases. Plain hotpot dùng Rule,
  hai cases còn lại production route gọi SLM. Không có external calls.
- Các adapters không thay đổi weights. New raw success phản ánh rule context
  đúng hơn; không chứng minh weights hết lỗi hoặc independent generalization.
- Cold load V3/V4: 78.10/57.56 s, riêng Torch import 9.69/6.37 s. Torch peak mỗi
  run ~2.13 GiB allocated /2.26 GiB reserved, 196 4-bit layers, 392 LoRA params,
  no meta, cache-only. Warm chỉ n=2, p95 không báo; observed p50=32.18/17.81 s,
  **không dùng chọn model/performance claim**. Host RAM/desktop VRAM contention
  khác baseline; có GPU observation ~3.85/4 GiB total in-use trong một attempt.
- `final/leakage-audit.json`: 36 test files/523 static message literals; train
  1.095, validation 151 nguyên vẹn; suite exact/normalized overlap=0, near=1.
  Existing static tests: exact=8, near=13. Diagnostics vẫn không độc lập; cùng
  semantic situations/near-duplicates giữ flags, không đổi denominator/labels.
- `final/protected-integrity.json`: 413 protected data/models/notebooks/frozen
  reports/shared/AI1/AI3/backend files hash-compared, 0 changes, sealed không đọc.
- `final/targeted-tests.txt` và XML: 1.153 passed/22 skipped/0 xfailed; original
  eight xfail assertions giữ nguyên; integration-demo.txt ở thư mục cha passed.
- `final/gemini-dry.json`, qwen32-dry.json, deepseek32-dry.json, qwen32-mock.json,
  deepseek-fallback-mock.json: budgets/calls configured, 0 external calls. Mock
  direct Qwen dispatch=3, historical V4 fallback DeepSeek dispatch=1; synthetic
  usage/cost không được coi là provider quality/billing measurements.
- `final/runtime-vs-head.patch`, git-status.txt: read-only Git evidence, bao gồm
  incoming work như đã nêu. Không stage/commit/push hoặc đổi branch. Final secret
  scan chỉ báo boolean/count, không in key; báo cáo không chứa configured secrets.
