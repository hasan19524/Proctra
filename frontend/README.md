# Procto — Frontend

Next.js (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui.

Part of the Procto monorepo — see the [root README](../README.md) and
[ARCHITECTURE.md](../ARCHITECTURE.md).

## Scripts

| Command             | Purpose                             |
| ------------------- | ----------------------------------- |
| `npm run dev`       | dev server on http://localhost:3001 |
| `npm run build`     | production build                    |
| `npm run lint`      | ESLint                              |
| `npm run typecheck` | `tsc --noEmit`                      |
| `npm run test`      | Vitest                              |
| `npm run format`    | Prettier write                      |
| `npm run check`     | lint + typecheck + test             |

## Structure

```text
src/
├── app/          # routes (app router)
├── components/   # ui/ (shadcn primitives) + feature components
├── lib/          # api client, ws client, utils
├── hooks/        # reusable hooks
├── stores/       # zustand stores
└── types/        # shared TS types
```
