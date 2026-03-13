# Frontend Application (Next.js)

This directory contains the frontend for the Deep Research Stock Trading Assistant.

## Tech Stack
- Next.js (Pages Router)
- React + TypeScript
- Tailwind CSS

## Main Page
- Chat UI: `/stock-assistant`

## Prerequisites
- Node.js 18+
- pnpm 9+
- Running backend API (`FastAPI`) at `http://localhost:8000` (or your custom URL)

## Environment Variables
Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## Install
From repository root:

```bash
cd frontend
pnpm install
```

## Run (Development)

```bash
cd frontend
pnpm run dev
```

Then open:
- `http://localhost:3000/stock-assistant`

## Available Scripts
- `pnpm run dev` - Start dev server
- `pnpm run build` - Production build
- `pnpm run start` - Run production server
- `pnpm run lint` - Lint command (may depend on Next/ESLint setup)

## API Integration
The chat page calls backend endpoints:
- `POST /api/chat/stream` (SSE streaming response)
- `POST /api/research` (non-streaming research response)

## Features
- Chat-style interface (user/assistant messages)
- Streaming assistant output (token/chunk updates)
- Multi-turn context forwarded to backend
- File attachment from UI (PDF/TXT/MD/CSV) for additional context
- Client-side upload guardrails (max 5 files, max 5MB each)
- Markdown-styled assistant responses
- Signals and sources shown per assistant response
- `New Chat` reset and `Download Markdown` export actions
- Optional MCP/A2A call configuration per turn (add/remove row builders in sidebar)

## Troubleshooting
- If you encounter Next cache issues after file moves:
  ```bash
  cd frontend
  rm -rf .next
  pnpm run dev
  ```
- Ensure backend CORS allows frontend origin (default expected: `http://localhost:3000`).
