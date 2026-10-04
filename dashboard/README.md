# HONEYMOON Dashboard

Live dashboard for the HONEYMOON engine: agent activity, posture gauge, event stream, reports,
findings, and the hardening ledger. Built with Next.js, Tailwind, Framer Motion, and Lucide.

## Running

The dashboard reads from the HONEYMOON daemon, so start that first from the repository root:

```bash
honeymoon serve --repo .     # WebSocket on 4200, HTTP on 4201
```

Then start the frontend:

```bash
cd dashboard
pnpm install
pnpm dev                     # http://localhost:3000
```

## Scripts

| Command | Purpose |
|---|---|
| `pnpm dev` | Development server |
| `pnpm build` | Production build (also type-checks) |
| `pnpm start` | Serve the production build |
| `pnpm lint` | ESLint |

The daemon binds to `127.0.0.1` only. The WebSocket client lives in `src/lib/ws.ts`.
