# UI (Next.js)

## Run

Recommended (from repo root):

```bash
make ui-install
make dev
```

UI-only mode (from repo root):

```bash
make ui-dev
```

Manual mode (inside `ui/`):

```bash
cd ui
npm install
npm run dev
```

## API mode

- Real backend:
  - create `ui/.env.local`
  - set `NEXT_PUBLIC_API_BASE=http://localhost:8000/v1`
- Mock fallback:
  - leave `NEXT_PUBLIC_API_BASE` unset
  - UI uses `/api/mock/v1`

## Tests

```bash
cd ui
npm run test
```

Covered critical flows:
- config save valid/invalid with warnings
- JSONL multiline/broken validation
- run + score/gate rendering
- CV generation + markdown preview
