# AI 2 Preference Schema v0.2

The public `PreferenceUpdate` is a turn delta. All fields default to empty containers:

```json
{
  "set_values": {},
  "add_hard_constraints": {},
  "add_soft_preferences": {},
  "add_semantic_preferences": [],
  "add_negative_preferences": [],
  "context_updates": {},
  "remove_preferences": [],
  "references": [],
  "relative_updates": {}
}
```

`UserPreferenceState` retains session_id, user_id, location, food, cuisine,
hard_constraints, soft_preferences, semantic_preferences, negative_preferences,
context, and reference_restaurants. Location remains top-level. Food and cuisine
are query intent, not constraints. Cuisine aliases such as Nhật map to japanese.

## Canonicalization and routing policy

AI2's shared `normalize_update` boundary is used after rule/provider/optional SLM
merging, before a final update or labeling candidate is returned, and by state
transitions. Exact alias tables cover Vietnamese, Korean, Japanese, Chinese,
Thai, Italian and Western cuisines, existing ambience/spicy labels, and the
explicit allergen aliases (peanut, seafood, sesame, milk, cashew, walnut and
pistachio). For example, `Hàn`, `đồ Hàn`, and `Korean`
converge to `korean`; `yên tĩnh` converges to `quiet`. Aliases deduplicate after
normalization, including replacement containers and known preference removals.

Known transport/occasion/meal-time values use the canonical context vocabulary
below; companions normalize known aliases but retain custom labels. Food names
such as `mì quảng`, unknown regional cuisines, and unknown semantic text remain
open vocabulary and are preserved verbatim. Cuisine aliases are not a closed
taxonomy. Extensible constraint keys and values (such as service_mode/dietary)
are not translated or assigned invented enums; known numeric/boolean fields keep
their existing strict validation. Ambiguous country words inside sentences need
cuisine evidence, rather than treating every `ý` or `Thái` as a cuisine request.

Rules consume recognized semantic spans, including attached category wording
such as `ngân sách`, `giá`, `khoảng cách`, or `món` when that category is actually
parsed. Only safe scaffolding is then removed from unmatched fragments. Negation,
conditions, alternatives, corrections and unknown modifiers remain residual and
request inference; category nouns are not globally erased. Bare filler is not
evidence of understanding. Fewer API calls must not sacrifice semantic recall.
Conjoined companion lists retain each stated group; relative events, absolute
precedence, safety exclusions and caller-owned reference IDs retain v0.2 semantics.

## Context and structured preferences

`context_updates` merges into state.context without replacing unrelated keys.
It accepts JSON primitives and lists, including custom keys. Objects, location,
and relative_updates are rejected in this delta. Known context fields normalize:

| Field | Canonical values |
| --- | --- |
| transport_mode | walking, motorbike, car, bicycle, public_transport, ride_hailing |
| occasion | casual, date, family, business, celebration |
| party_size | Positive integer; booleans are invalid |
| companions | Array, e.g. alone, partner, friend, friends, family, children, colleagues |
| meal_time | breakfast, lunch, dinner, late_night |

Only stated information is extracted. Transport never implies parking.
“Tôi đi xe máy” supplies transport_mode=motorbike only. “Phải có chỗ gửi xe”
supplies hard parking=true; “có chỗ gửi xe thì tốt” supplies soft parking=true.
Deterministic explicit parking evidence overrides contradictory model inference.

Hard constraints are mandatory filters; soft preferences express wishes.
Both dictionaries remain extensible. Common keys include budget_min, budget_max,
max_distance_km, max_travel_time_min, min_rating, parking, wifi, air_conditioning,
outdoor_seating, wheelchair_accessible, service_mode, dietary, allergens_excluded,
spice_level and open_at. Do not create top-level fields for these attributes.

Semantic preferences hold unstructured ambience/conversation concepts. Numeric
distance remains structured. Negative preferences express dislikes (spicy);
allergies are hard exclusions (allergens_excluded=["peanut"]).

## State and precedence

Sets, hard constraints, soft preferences, semantic preferences, negative
preferences, and context updates are merged into an independent snapshot.
Removals beat additions. References retain deterministic caller-result resolution.
Hard constraints beat redundant soft values, including replacement containers.
Explicit form values retain priority over NLP removals and relative interpretation.

Optional form extensions: `item_kind` (`food`/`beverage`) and `serving_style`
(nonempty list of `dry`, `broth`, `soup`, `hotpot`, `unknown`). Explicit “món nước”
sets food plus broth/soup styles; “đồ uống” selects beverages and clears stale
styles. These keys live in `hard_constraints`; see [taxonomy](serving_taxonomy.md).

Absolute budget/distance settings suppress same-turn relative directions.
“Gần hơn” is a relative distance decrease; “gần gần” is soft distance=near.
Walking supplies transport context, with explicit minutes/distance represented by
max_travel_time_min/max_distance_km.

Relative updates are **turn-level events**. No arithmetic policy is invented:
directions remain available in the returned PreferenceUpdate and interaction logs
for downstream results processing. They are never accumulated in state.context.
Every transition also purges legacy context.relative_updates, even malformed values.

Removals accept paths such as hard_constraints.budget_max,
soft_preferences.parking, and context.transport_mode. Legacy numeric limit names
resolve to scopes present in the state/update (both when ambiguous), defaulting
to hard paths when no scope evidence exists. Other legacy labels remain accepted; an
unqualified parking removal removes both constraint scopes. Whole food/cuisine
removal is supported. Input objects are not mutated.

The [High Audit](AI2_V02_HIGH_AUDIT.md) records subsequent correctness fixes:
removals precede conflict cleanup; deterministic numeric evidence is protected
unless a later unresolved correction changes the same attribute; hard allergen
additions accumulate until explicit replacement/removal. Known constraint values
are validated consistently at public and provider boundaries. Legacy relative
events are removed from inference-state copies as well as new state snapshots.

## Shared provider output and frozen SLM

```text
Rule (sufficient -> update)
  -> Local SLM (disabled for now)
      -> External LLM fallback
  -> Normalization
  -> State Manager
```

Unresolved input with SLM disabled goes directly to the existing Gemini/OpenAI
flow. The disabled path does not import SLM modules, initialize models, load files,
or invoke an SLM. No heavy ML dependencies are added.

SLMInput contains message, current_state, full rule_result and previous_results.
SLMParseResult contains a v0.2 update, finite confidence in [0,1], should_fallback,
and JSON metadata. A validated result at or above the configured threshold is
merged and normalized. Uncertainty, invalid output and exceptions fall back once
to the external provider. References use the same deterministic resolution.

The factory in conversation/slm/router.py is the future backend extension point.
The only implemented backend is disabled: explicitly enabling it reports
disabled_backend and safely falls back. Unknown backends report slm_unavailable.
No /provider slm command exists; SLM is an intermediate layer.

Metadata adds slm_enabled, slm_called, slm_backend, slm_confidence, slm_fallback,
slm_error and slm_ms. Disabled status is false/false/0. Existing timing fields
remain, and parser_used may additionally be hybrid_slm.

Gemini and OpenAI share StructuredPreferenceUpdate. Its strict wire format uses
context key/value entries, converted into the public context_updates dictionary.
The wire schema requires the field; legacy local fixtures can omit it. Provider
network/retry behavior is unchanged.

## Data migration and validation

Interactive records and training exports carry schema_version="0.2". The public
PreferenceUpdate does not. Old deltas default context_updates to {} on validation
and export. Export normalizes shape only: historic semantic labels are not moved
or relabeled. Only accepted/corrected records are exported. Corrections accept
context_updates through the same validated contract.

`python scripts/check_ai2_slm_dataset.py --check-data PATH.jsonl` checks version,
input/target shape, reviewed labels, duplicates and field frequencies. It rejects
unversioned datasets with a re-export instruction. It never trains, imports ML
runtimes, downloads weights or calls APIs.

Unit expectations for persistent relatives, same-turn absolute/relative pairs,
date context, canonical removal paths, versioned exports and deterministic
parking were intentionally migrated. The 105-prompt benchmark source is frozen;
historical semantic-date expectations can differ from v0.2 context extraction.
