# Shared interface 0.2

The web search now returns one representative menu result per restaurant, with
additive `recommendation_group`, `food_match`, `candidate_rank`, `reason_features`,
`eligible_menu_items`, `explanation`, `explanation_source`, and `catalog_only` fields.
`named_food_query` distinguishes named search from general recommendations.
The retired `explanation` and `explanation_source` fields remain null for response
compatibility. Search makes no LLM request after ranking. See the
[budget/chat final handoff](AI2_BUDGET_CHAT_FINAL.md) for the current behavior.
Top-K counts restaurants; IDs keep their original restaurant/menu/dish meanings.
Eligible menu entries reuse canonical `RankedResult`, including original candidate
rank and score. Shared Pydantic schemas remain unchanged. The standalone pipeline
uses the same post-ranking selection; backend/frontend/AI1/AI3 owners should review
these coordinated semantics before merging. See [final contract/runbook](RESTAURANT_RECOMMENDATION_FINAL.md).

The web conversation endpoint also exposes the additive intent/reply contract in
[AI2 LLM-first](AI2_LLM_FIRST.md). The shared preference, candidate, ranked-result
and recommendation schemas below are unchanged.

Canonical definitions: `src/common/schemas.py`. `AI_INTERFACE_VERSION = "0.2"`
lives in `common.constants`; no mandatory version field was added to envelopes.
Preference Schema v0.2 remains exactly the implemented AI 2 contract documented
in [AI2_PREFERENCE_SCHEMA_V02.md](AI2_PREFERENCE_SCHEMA_V02.md).

## Imports and callable interfaces

Installed packages retain their existing src-layout names:

```python
from common.schemas import (
    UserRequest, PreferenceUpdate, UserPreferenceState,
    Candidate, RankedResult, FeedbackEvent, RecommendationResponse,
)
from conversation import parse_user_input, update_state
from retrieval import retrieve_candidates
from ranking import rank_candidates
from pipeline import recommend
```

From a repository checkout after installation, the equivalent `src.common.schemas`,
`src.conversation`, `src.retrieval`, `src.ranking`, and `src.pipeline` public imports
also work. `src/__init__.py` aliases them to the same modules/classes, avoiding
competing Pydantic types. `src` is a checkout compatibility namespace, not the
installed distribution name. Use canonical names for all internal submodules and
code running outside the checkout; no AI 2 import rewrite was required.

`common.interfaces` defines callable Protocols (no inheritance required):

```python
parse_user_input(request: UserRequest) -> PreferenceUpdate
update_state(current_state: UserPreferenceState | None,
             update: PreferenceUpdate, session_id: str,
             user_id: str | None = None) -> UserPreferenceState
retrieve_candidates(state: UserPreferenceState, top_k: int = 100) -> list[Candidate]
rank_candidates(state: UserPreferenceState, candidates: list[Candidate],
                top_k: int = 10) -> list[RankedResult]
recommend(request: UserRequest) -> RecommendationResponse
```

The Protocols are named `ConversationModule`, `StateManager`, `RetrievalModule`,
and `RankingModule`, respectively. Bind either functions or callable objects.

## Existing AI 2 schemas

`UserRequest` keeps session_id, optional user_id/message/current_state, default
form, and previous_results. Its `PreviousResult` contract is unchanged.
`PreferenceUpdate` retains all nine fields: set_values, add_hard_constraints,
add_soft_preferences, add_semantic_preferences, add_negative_preferences,
context_updates, remove_preferences, references, relative_updates.

`UserPreferenceState` retains session/user identity, location, food, cuisine,
hard/soft constraints, semantic/negative preferences, context and reference
restaurants. Normalization, canonical removals, form priority and state-copy
semantics remain owned by AI 2. Relative updates are events in the originating
turn delta; they are not persisted or replayed from state. The pipeline passes
only state downstream and does not invent numeric adjustments for relative
feedback. Any later policy for handling those events requires team review.

## Candidate: AI 1 -> AI 3

| Field | Contract |
| --- | --- |
| restaurant_id | Required nonempty opaque string |
| menu_item_id | Optional nonempty string; absent only for restaurant-only results |
| dish_id | Optional nonempty canonical dish ID where the source provides one |
| restaurant_name, dish_name | Optional source display strings |
| location | Optional source coordinates; lat [-90,90], lon [-180,180] |
| distance_km | Nonnegative finite km; may be absent only without user location |
| price | Nonnegative integer VND; absent only when source price is unavailable |
| restaurant_features | Extensible JSON dictionary, e.g. rating/cuisine/provenance |
| match_features | Extensible JSON dictionary, e.g. semantic_similarity/food_similarity |

Null is unknown, not zero. Candidate alone cannot validate source provenance or
user-location availability: AI 1 must enforce those conditions using state/data.
Do not fabricate distance when source coordinates are missing; exclude that row
when a distance constraint cannot be checked and document missing-data policy.
Document supported filters and unknown attributes rather than claiming unknown
allergen/facility evidence satisfies a hard constraint. Similarity feature names
are suggestions, not required fields or an embedding-model choice.

## RankedResult: AI 3 -> backend

Preserve restaurant_id/menu_item_id/dish_id exactly from the input candidate.
Required rank is a positive one-based integer; score is a finite float, with no
probability range imposed. Optional names, price, distance and rating (0..5) come
from source data. `reason_features` is an extensible JSON dictionary.

AI 3 returns at most top_k results in rank order, ranks 1..N, with no invented
candidate IDs. Score scale/tie policy and missing features are AI 3's documented
responsibility. Switching a baseline for LightGBM/XGBoost must not change the
envelope. JSON validation alone does not prove list ordering, provenance or model
quality; AI 3's implementation tests must check these.

## Feedback and response

`FeedbackEvent`: session_id, optional user_id/restaurant_id/menu_item_id, nonempty
action, optional message/rank_position (one-based). Known actions include view,
click, save, choose, reject, too_far, too_expensive and text_feedback. Action is
an open string so backend extensions need no enum change. This is an envelope;
no persistence or action-to-preference policy is implemented here.

Backend routes user-authored feedback text as a new `UserRequest` with the prior
state and caller-supplied `PreviousResult` objects. Project supported previous-
result fields explicitly; `RankedResult` has additional fields and must not be
blindly unpacked into AI 2's closed `PreviousResult` schema. Copy IDs verbatim;
never infer or renumber identifiers. The backend retains dish_id in its original
results because existing AI 2 PreviousResult does not contain that field.
Retrieval/ranking then rerun through `recommend`. Interpreting action-only events
is a future agreed policy, not an implicit state change in this scaffold.

`RecommendationResponse` requires session_id, state and results. The orchestrator
preserves session identity and rejects inconsistent request/current_state identity
before parsing. No metadata fields are required.

## Injection, readiness and validation

`recommend` optionally accepts retrieve_fn, rank_fn, parse_fn, update_state_fn and
`PipelineConfig` (positive retrieval_top_k=100/ranking_top_k=10). Defaults resolve
the public functions at call time. AI1 retrieval and AI3 CatBoost ranking are
implemented; real runs require the artifacts documented in [setup](setup.md). Default parsing follows existing AI 2 environment configuration;
offline callers use the explicit disabled configuration shown in
`examples/integration_demo.py`. The demo never loads `.env`.

All new contracts reject extra envelope fields and non-finite numeric values;
feature containers accept JSON values only. Run the full suite and demo after
shared edits. Tests cover JSON round trips, invalid fields, import identity,
side-effect-free cold imports, injected flow, IDs and AI 2 multi-turn semantics.
Changes require coordinated review, documentation and contract-test updates.
# Optional serving taxonomy form fields

`UserFormInput.item_kind` accepts `food` or `beverage`; `serving_style` accepts a
nonempty list drawn from `dry`, `broth`, `soup`, `hotpot`, `unknown`. Explicit form
values override message interpretation. A beverage form clears a previous style
unless a style is explicitly supplied. AI1 treats these as hard constraints;
legacy datasets must be upgraded before using them. Existing fields stay valid.
See [taxonomy documentation](serving_taxonomy.md) for artifact and display metadata.

## Search map results

`POST /api/search` optionally accepts `include_map_places: true`. The response
then includes `map_places` (`id`, `name`, `dish`, `lat`, `lon`, nullable
`distance_km` and `price_vnd`), independently of
the ranked `results` and their `top_k`. Map matches use the same parsed state,
hard filters and restaurant exclusions, require a lexical dish-name match when
food is specified, and contain one entry per restaurant with valid coordinates.
There is no top-12 or top-100 map cutoff. Soft preferences continue to affect
the ranked list; map pins represent food/hard-filter matches, not ranking scores.
Without the opt-in, `map_places` is null and older consumers retain their behavior.
The search UI requests 12 ranked results and the complete map set in one turn.
