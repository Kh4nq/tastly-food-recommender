# Homepage presentation refactor

The existing HeroSection, CategoryChips, TodayRecommendations, DishCard,
SpinSection/SpinPanel/SpinResultCard, MoodSection and Footer were inspected and
refactored in place. Existing cream/brick/gold/ink tokens, typography, pill buttons,
warm borders, illustrations, localization and state hooks are reused.

`lib/home-layout.ts` supplies the shared `max-w-7xl` container with 16/24/40px
responsive padding. Homepage section spacing is controlled by the page's
48/64/80px scale rather than separate section margins. The footer uses the same
container. Existing button classes are shared through `buttonClassName` so links
and the Button component keep one visual convention.

- Hero: compact 55/45 desktop layout, balanced two-line heading, search CTA and
  an anchor to today's picks. The latest visual pass uses a real pho photograph
  and a smaller banh-mi skillet photograph from Explore. Categories sit outside the hero in a single horizontal
  strip; categories and recommendations share tighter spacing below the hero.
- Recommendations: four desktop/two tablet columns and an 86%-width mobile
  carousel. Cards use a 3:2 image, compact restaurant/distance line, compact
  rating/price row and a dash for unknown ratings. Per the follow-up UI request,
  menu/price helper paragraphs below the grid are omitted. Their API metadata is
  retained without changes.
- Food visuals: hero uses existing Explore photographs; recommendations and
  spin results reuse the food-category emoji style from the spin buttons.
  Mood retains its existing food illustration.
- Spin: one brick accent container with a 5/7 split. The existing category picker
  and random-selection hook remain; the result uses a matching food emoji.
- Mood: heading/chips sit together, followed by a maximum 768px recommendation
  card, related-dish chips and a nearby CTA.
- Footer: narrower brand/contact area, four existing link groups (four links
  each), then a separate copyright row. Existing link destinations are preserved;
  no placeholder legal routes or new pages were introduced.

The recommendation API, selected-location state, search routes, spin pool/timing,
mood-to-dish mapping and backend code are unchanged by this layout work.

Validation uses TypeScript, frontend ESLint, production build, and the existing
renderer regression workflows. Homepage regression now also exercises the hero
and footer rendering, category toggles, spin lifecycle and resulting search link,
plus mood selection and its search CTA. Browser visual QA remains unavailable
without a connected browser session.
