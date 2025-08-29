# Repository Guidelines

## Project Structure & Modules
- `app/`: App Router pages and routes (e.g., `app/quickstart/page.tsx`).
- `components/`: Reusable React components (PascalCase, e.g., `DocsSidebar.tsx`).
- `public/`: Static assets served at `/`.
- `utils/`: Small helpers (e.g., `utils/copyAllDocs.ts`).
- Config: `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, Tailwind 4.

## Build, Test, and Development
- `npm run dev`: Start local dev server with Turbopack.
- `npm run build`: Production build (`.next/`).
- `npm start`: Run the built app.
- `npm run lint`: ESLint via Next.js rules.

Examples:
```
# develop
npm run dev
# validate before PR
npm run lint && npm run build
```

## Coding Style & Naming
- TypeScript, strict mode enabled; prefer explicit types for public APIs.
- React components: PascalCase files and exports (`Navigation.tsx`).
- Route segments: kebab-case folders with `page.tsx` (`app/blog/trust-keyword/page.tsx`).
- Indentation: 2 spaces; avoid trailing whitespace.
- Styling: Tailwind CSS v4; prefer utility classes over ad-hoc CSS.
- Linting: fix issues surfaced by `npm run lint` before committing.

## Testing Guidelines
- No unit test framework configured yet. Use:
  - Type checks: `tsc --noEmit` (implicit via Next build).
  - Lint/build as acceptance gates: `npm run lint && npm run build`.
- If adding tests, follow React Testing Library + Vitest/Jest patterns and mirror `app/` or `components/` structure (e.g., `components/Navigation.test.tsx`).

## Commit & Pull Requests
- Commits: prefer Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`). Keep messages imperative and scoped (e.g., `feat(docs): add quickstart examples`).
- PRs must include:
  - Clear description, motivation, and screenshots/GIFs for UI changes.
  - Linked issue (if applicable) and checklist: `lint` + `build` passing.
  - Scope small and focused; avoid unrelated refactors.

## Security & Configuration
- Secrets: never commit them. Use `.env.local` (gitignored). Example: `DISCORD_WEBHOOK_URL=...`.
- Validate external links and untrusted content. Do not expose internal env values to client components.
- Static assets go in `public/`; avoid importing large binaries into the bundle.

## Adding Content
- New docs page: create a route under `app/<section>/page.tsx` and reuse shared components (e.g., `CommandBlock`, `DocsSidebar`). Keep titles concise and URLs kebab-case.
