# Serving and restaurant space metadata (serving-space-v1)

Both food and beverages are retained. `item_kind` distinguishes `food` from
`beverage`. Food `serving_style` is `dry`, `broth`, `soup`, `hotpot`, or `unknown`;
beverages use `not_applicable` in the dataset.

AI2 interprets explicit “món nước” as `item_kind=food` and
`serving_style=["broth", "soup"]`. Hotpot remains separate. “Món khô” selects
`dry`; “đồ uống/nước uống” selects beverages and clears an earlier style constraint.
AI1 applies these constraints before retrieval scoring; AI3 ranks eligible items.
The API form supports the same optional `item_kind` and `serving_style` fields.
Unknown styles do not satisfy an explicit broth/soup/dry request. Missing taxonomy
in a legacy dataset raises an actionable constraint error rather than guessing.

`scripts/update_serving_taxonomy.py` adds conservative classifications, evidence
and version fields without changing source IDs, menu associations or original
descriptions. It validates the old release, keeps a backup under `data/backups`,
and writes aligned processed files, source hashes, profile manifest, dataset card,
embedding metadata and `data/ai1-demo-data.zip` with a complete checksum manifest.
Ambiguous noodles and desserts remain unknown until reviewed. This is inference,
not manually verified ground truth; a cooking method alone is insufficient.

Restaurant `space_description` and JSON `space_tags` are generated from the
existing explicitly synthetic demo profiles. `space_source` records
`synthetic_demo:restaurant_profiles`. No unsupported luxury/decor claims are
invented. These columns are available in PostgreSQL and API result fields; they
are display metadata, not verified venue evidence or new ranking signals.

Embedding reuse is allowed only after proving that every original per-ID
`restaurant_text` and `dish_text` is exactly unchanged. The added filter/display
columns are outside those text templates. Changing a template or putting space
descriptions into semantic matching requires rebuilding the affected vectors.

After producing the release, apply `database/schema.sql`, `indexes.sql`, and
`procedures.sql`, then seed the local development catalog and restart the backend
to invalidate its cached retriever. Keep these large private artifacts out of Git.
