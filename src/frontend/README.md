# Tastly frontend

Next.js 16 / React 19 with Tailwind CSS. See the [project README](../../README.md) for dataset, backend, database and OpenRouter setup.

From this directory:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:3000. The production FastAPI backend must run separately on port 8000. `/api/*` is proxied through Next.js; `BACKEND_URL` can change its destination.

Optional `.env.local` variables: `BACKEND_URL`, `NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN` (public Mapbox token), `NEXT_PUBLIC_WEB3FORMS_ACCESS_KEY` (public contact key). The default Leaflet/OpenStreetMap map needs no token. Never put backend LLM secrets in public variables. Existing map attribution is retained.

```powershell
node --test tests/*.test.mjs
npm.cmd run lint
npm.cmd exec tsc -- --noEmit
npm.cmd run build
npm.cmd start
```

The build fetches Google Fonts. The npm lockfile is authoritative; generated `.next`, `node_modules`, type declarations, caches and `.env.local` are not committed. Some peripheral pages have illustrative content.
