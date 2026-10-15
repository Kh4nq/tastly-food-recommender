# Local UI, search and account fixes — 2026-10-14

Baseline: `fullstack-dat` at `8079c37`; changes applied locally on
`fullstack-UI` after pulling `fullstack` at `1ec9ca4`.

## Resulting behavior

- Opening `/search` without search parameters shows a warm welcome panel with
  four quick dish suggestions. It sends no recommendation request and initializes
  no map. Submitting the search form or opening a link with search parameters
  starts search; an existing map is retained if navigating back to the welcome.
- Welcome hero uses a compact 55/45 layout within 1200 px, an embedded three-field
  Next Form, larger photo suggestions, and a three-photo food collage from existing
  public assets. It replaces the top filter bar only before a search starts.
  The catalog count and featured Hanoi pho restaurant were read from PostgreSQL
  on 2026-10-14; the price is labelled indicative because it is not verified.
  No star rating or distance was invented. Collage/thumbnail images are illustrative.
- Preserve the restaurant cards, filter semantics, loading illustration, list/map
  layout and browser-local favorites from the saved UI.
- Keep Next Form client navigation. Keep ResultExplorer and the map mounted
  during loading, successful searches, empty responses and errors. Only replace
  markers and the search location after the current response succeeds.
- Restore wheel zoom in both Mapbox and Leaflet. Leaflet fits new points immediately.
- Derive loading and selected/hovered markers from the current request/results,
  removing synchronous effect state resets. Abort superseded requests and ignore
  their late responses. A 50 ms window coalesces rapid changes and avoids Strict
  Mode issuing duplicate searches. Search still resets its anonymous preference
  session before requesting recommendations, preserving existing filter behavior.
- Favorite actions verify `/api/auth/me`, rather than reading an HttpOnly cookie.
  Invalid sessions open the existing login dialog with a return-to-search URL.
- Header verifies the current user. Server-side user lookups are memoized only
  within the React request, not across users. Logout errors are displayed.
- Local auth accepts both localhost and 127.0.0.1 on port 3000 by default.
  Explicit `BACKEND_CORS_ORIGINS` continues to override those defaults.
- Auth cookie expiry matches the configured account session lifetime.
- Existing settings and role-aware profile pages remain connected to the real API.

## Validation

- Frontend TypeScript, full ESLint and production build passed.
- Backend: 158 passed, 23 skipped. PostgreSQL integration tests that require
  their opt-in environment remain skipped; live API checks below used local PostgreSQL.
- `scripts/frontend-regression.cjs`: React lifecycle tests verified map persistence,
  empty/error responses, stale-response protection, rapid request cancellation,
  Strict Mode request coalescing, and favorite save/remove/login behavior.
  MapboxView was exercised with a mock Mapbox engine: one map instance remained
  while GeoJSON markers changed or cleared. This does not verify external map tiles.
- Live frontend-proxied API checks used temporary customer and business accounts:
  register, HttpOnly cookie, profile/settings pages, profile update, password
  rotation, rejection of the old password, login from both local origins, logout.
  Only accounts created by these checks were removed afterward.
- Live search: phở under 50k returned 12 coordinate-bearing results in 3.44 s;
  phở around HCM within 5 km returned 12 in 0.85 s; drinks under 30k returned 12
  in 0.95 s; budget 1 VND returned zero in 0.25 s. Returned prices respected the caps.
  These are individual local CPU timings, not a before/after retrieval benchmark.

## Run and test

Web: http://localhost:3000/search?dish=pho&maxPrice=50000&city=hcm

Backend: http://127.0.0.1:8000/ready

Both services run in the background; Next dev reloads frontend edits.
Backend uses CPU with local Qwen and external LLMs disabled.
Logs are in the ignored `logs/` directory (`frontend-fixed.*`, `backend-fixed.*`).

For the optional frontend regression runner:

```powershell
# Install the optional renderer outside the project package dependencies:
npm install --prefix ..\tmp\ui-regression --no-save --no-audit --no-fund react-test-renderer@19.2.8
node scripts/frontend-regression.cjs ..\tmp\ui-regression
```

Manual checks: search different dishes/areas, rapidly change a search, try an empty
result, use list/map on mobile, zoom the map, sign in then save/remove a favorite,
update settings, change password and sign out.

Favorites retain browser-local persistence; account-specific server storage is
not implemented. Retrieval/ranking algorithms, datasets and the local Mapbox token
were not changed. Local environment files and credentials remain excluded from Git.
