# Tastly food assistant

The floating assistant starts closed. Opening it shows the existing chef mascot,
a short welcome and four send-on-click suggestions. Closing the panel preserves
the current messages. There is one active conversation and no saved-thread UI.

The panel grows with its content, capped at 380px wide and 560px tall on desktop.
Small screens use the available width; VisualViewport resize/scroll events adjust
the panel above the on-screen keyboard. The message body scrolls independently.
Replies follow the bottom only while the reader is near it. A latest-message
button lets a reader return after scrolling up. Enter sends, Shift+Enter inserts
a newline, and composing text is not submitted.

## Backend integration

- SearchPreferenceProvider, mounted inside SearchLocationProvider in the app
  layout, owns the shared preference draft, results and request lifecycle.
  Chat owns only its transcript and presentation. SearchBar renders and edits
  the shared draft directly; SearchResult only projects shared results.
- The draft uses the snake_case UserPreferenceState contract from
  common.schemas. No common schema or AI2 parser behavior changes. Coordinates
  are derived from SearchLocationProvider, which remains the sole owner of the
  selected origin and its persistent label/address.
- lib/conversation-state.ts contains pure projection and request helpers.
  buildSearchRequest sends the shared snapshot as optional preference_state to
  POST /api/search. The HTTP adapter reuses UserPreferenceState and existing
  known-constraint validation. The service binds session/user identity from its
  cookie/session record before supplying that baseline to AI2.
- A chat message is applied on top of that snapshot. Old absolute constraints
  are not sent through form, because form overrides NLP. The normalized full
  backend response replaces the shared draft. This also lets manual chip
  removal take effect without deleting the whole session. Legacy API clients
  omitting preference_state continue to use stored session state.
- Valid recommendation responses navigate to /search?intent=<opaque id> and
  reuse the already-fetched results/map places. The chat shows a short summary;
  it does not trap the full results or start a second retrieval on navigation.
  Search intent uses the existing clarification_required flag and normalized
  preference/results evidence; the API does not expose a separate intent enum.
- URL filters are explicit entry actions, merged only for provided fields.
  Session-local snapshots (up to 20 searches) support back/forward. Neither
  coordinates nor chat text enter URLs. Unknown/expired history tokens do not
  restore cleared state. Refresh does not persist the chat archive.
- Missing location retains the original message and shared filters, opens the
  existing picker and performs no search yet. Selecting an origin resumes that
  explicit pending request once. Passive location changes without pending
  intent never trigger a food search. An explicitly changed backend coordinate
  may update the selector, unless a newer manual selection has already won.
- Start over uses DELETE /api/session, with inline confirmation after meaningful
  messages or existing preferences. Local history clears only on success.
  A failed reset keeps the conversation available for retry.
- Reset clears shared food/cuisine/constraints/preferences/context, results and
  in-session search snapshots. It preserves location, login and language.
  Normal searches no longer call newSearch/DELETE. Newer manual edits abort
  in-flight requests so stale responses cannot overwrite them. Until Apply,
  the result view explicitly indicates that edited filters have not been run.

## Checks

Run from the repository root:

    node scripts/chat-regression.cjs ../tmp/ui-regression
    node scripts/search-state-regression.cjs ../tmp/ui-regression
    node scripts/location-regression.cjs ../tmp/ui-regression
    node scripts/frontend-regression.cjs ../tmp/ui-regression
    node scripts/home-recommendations-regression.cjs ../tmp/ui-regression

The renderer dependency must be installed in the supplied directory.
chat-regression delegates to search-state-regression. It mounts the real location
and preference providers, API client, chat, filters and search-page entry against
mocked HTTP. It covers manual/chat edits in both directions, removal, stale
responses, state-driven navigation without duplicate search, back/forward,
location stability/resolved updates, missing-location resumption, reset
cancel/failure/success, keyboard viewport sizing and first-load Strict Mode.
Backend tests additionally exercise the real offline AI2 parser with snapshots,
cookie identity binding, constraint validation and backward-compatible clients.
Renderer checks do not replace visual checks in a real mobile/desktop browser.
