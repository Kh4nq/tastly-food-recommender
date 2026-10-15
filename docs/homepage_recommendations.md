# Homepage recommendations — 2026-10-15

The homepage replaces its mock district-based trending grid with **Bữa ngon cùng
Tastly**, a location-based preview. The subtitle is “4 món ngon đáng thử quanh vị
trí bạn đã chọn”. The weekly featured banner is no longer mounted. Other homepage
sections keep their existing layout and behavior.

`TodayRecommendations.tsx` observes the shared `selectedSearchLocation`. It fetches
up to four cards, aborts superseded requests, and ignores stale responses. Changing
location only refreshes this homepage preview; it never navigates, opens chat,
changes the selected location, or calls the food-search/session endpoints.
“Xem tất cả” is an explicit link to the food-search page using the selected origin.

The preview uses the shared centered 1280px maximum width and 16/24/40px
horizontal padding, four desktop columns, two tablet columns, and a horizontal
mobile carousel. Cards share a 3:2 image ratio, restrained category labels and
compact price/rating/distance metadata. See `homepage_layout.md` for the layout refactor.
Four matching skeletons cover loading; missing location, empty catalog and
request failures have separate friendly states. Sparse responses show actual
cards and adjusted copy rather than fabricated slots.

## Read-only catalog endpoint

`GET /api/recommendations/today?lat=...&lon=...&limit=4&min_rating=4.5`

- Requires finite coordinates; limits output to four and radius to 1–20 km.
- Default radius is 10 km; it does not filter by district or province equality.
- Queries up to 200 nearby eligible restaurants with food menu entries, then
  ranks valid menu candidates by rating tier, rating descending, distance
  ascending, and review count descending.
- Prefers ratings greater than 4.5, then at least 4.3. If there are still fewer
  choices, lower/unknown ratings can fill available cards and remain labelled.
- Prefers distinct restaurant names and dish names, relaxing diversity only
  if necessary. Original database IDs remain unchanged.
- Does not call AI1/AI2/AI3, reset preferences, or issue anonymous session cookies.
- Does not alter the database schema, datasets, model files or dependencies.

## Current data limits

Live inspection found 26,025 restaurants and no `rating`, `review_count`, or
`image_url` columns. Missing ratings/reviews remain null; there are no invented
stars or counts. Optional future metadata is read when available. The current
menu catalog includes simulated/demo entries: the API exposes `is_synthetic`,
menu and price verification flags remain available in the response. The follow-up
UI request removes the explanatory menu/price paragraphs below the grid.
Dish-aware SVG illustrations are labelled illustrative when no
verified image is available. This is location-based catalog
selection, without a learned taste profile.

## Validation

```powershell
.venv-local/Scripts/python.exe -m pytest -q tests/backend -p scripts.sealed_benchmark_guard
node scripts/home-recommendations-regression.cjs ../tmp/ui-regression
node scripts/frontend-regression.cjs ../tmp/ui-regression
node scripts/location-regression.cjs ../tmp/ui-regression
cd src/frontend
npx tsc --noEmit
npm run lint
npm run build
```

Backend tests cover rating fallback, geographic boundaries, variety, duplicate
place names, null metadata, request validation and absence of session-cookie
side effects. Renderer tests cover location updates, four skeletons/cards,
unknown metadata, cancellation/stale responses, retries, empty and sparse data.

Live frontend-proxied API checks returned four recommendations near HCM and
Hanoi with four distinct dishes. An origin at 0,0 returned an empty list.
Homepage HTTP checks confirm the new title and absence of the old trending title
and weekly banner. No connected browser was available for visual QA.
