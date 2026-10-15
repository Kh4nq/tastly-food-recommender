# Search location controller

The header location chip opens a native dialog (bottom sheet on small screens).
Changing its selection writes app state and persistence only. It never changes
the route, active tab, or issues a food search.

`components/location/SearchLocationProvider.tsx` exposes `useSearchLocation()`:

- `currentDeviceLocation`: GPS position obtained in this mounted app session.
- `selectedSearchLocation`: active origin, with `lat`, `lon`, `address`,
  `shortLabel`, and `source: 'gps' | 'manual'`.
- `openLocation(true)`: ask for an origin before a location-dependent action.
- `selectLocation(...)` and `locate()`: explicit selection and GPS actions.

First visit requests browser GPS once, including under React Strict Mode. Failure,
denial, timeout, or unavailable GPS opens the dialog. A restored selection avoids
another permission request. Selected/recent locations persist in browser storage;
the selected origin is also written to the existing `loc` cookie for server reads.
Recent history is capped at three unique locations, most recently chosen first.
Reselecting a place moves it to the front; overlong/duplicate saved history is
trimmed on restore. Tiny coordinate changes or the same address do not add copies.
Legacy district/GPS cookies are migrated. Device state stays separate from a manual
search origin. A late GPS/reverse-geocoding response cannot overwrite a subsequent
manual selection.

SearchBar and SearchWelcome open this same selector instead of owning separate
city/district state. SearchPreferenceProvider now snapshots the selected origin
for the shared request and preserves results/map on passive location changes.
An explicit pending search/chat request blocked by a missing origin resumes once
the user selects a location; its original message and filters are retained.
Otherwise selecting a location never triggers a food search. Chat, filters and
the results page share UserPreferenceState; see [chat integration](chatbox_ux.md).

Address autocomplete and GPS reverse lookup use the existing
`NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN`. Persisted results request `permanent=true`;
the Mapbox account must support permanent geocoding. See
https://docs.mapbox.com/api/search/geocoding/. Requests are debounced, timed out,
and superseded responses are ignored. If unavailable, local city/district centre
suggestions still work; GPS keeps its exact coordinates with a coordinate label.
Area-centre suggestions are labelled as such rather than presented as exact addresses.

The city buttons now open a compact ward/commune dropdown. The bundled 2025
boundary snapshot includes all 168 units of HCM (113 wards, 54 communes, one
special administrative unit) and all 126 units of Hanoi (51 wards, 75 communes).
Names can also be typed without accents in the address input, with local current
administrative names shown before external geocoder results. Old district names
are retained only for legacy-cookie compatibility.

`lib/administrative-areas.json` contains names/codes and points inside the existing
AI1 post-merger boundary polygons, not fabricated street addresses or legal
administrative headquarters. Each choice is labelled a representative area point.
The large boundary files are not copied into the frontend. Name references:

- https://tphcm.chinhphu.vn/danh-sach-chinh-thuc-168-phuong-xa-cua-tphcm-sau-sap-xep-101250617000144317.htm
- https://hanoi.gov.vn/bo-may-chinh-quyen-thanh-pho-ha-noi

Validation on 2026-10-15:

```powershell
cd src/frontend
npx tsc --noEmit
npm run lint
npm run build
cd ../..
node scripts/frontend-regression.cjs ../tmp/ui-regression
node scripts/location-regression.cjs ../tmp/ui-regression
```

The renderer is the existing optional test dependency in `../tmp/ui-regression`.
Regression coverage includes GPS denial/unavailability, persistence, validation,
legacy cookies, Strict Mode, late reverse lookup, no automatic search, preservation
of results/maps, explicit retry, missing-location gates, chat coordinates, modal
semantics, arrow/Enter selection and the native dialog cancel handler.

Live local checks: `/contact`, `/search`, and a parameterized search page return
HTTP 200. A frontend-proxied search at 10.7843, 106.6844 returned three restaurants
within 5 km in 2.89 seconds and echoed the exact origin in response state.

Limitations: real Mapbox geocoding was not verified because credential-bearing
network verification was rejected by automatic approval review. No connected
browser was available for visual QA or verification of native focus trapping,
permission prompts and mobile layout. Those remain manual browser checks.
