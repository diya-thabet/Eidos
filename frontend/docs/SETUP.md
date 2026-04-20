# Frontend Setup Guide

## Prerequisites

- Node.js 18+ (20 recommended)
- pnpm (or npm/yarn)

## Quick Start

```bash
cd frontend
corepack enable      # enable pnpm
pnpm install         # install dependencies

# Copy environment file
cp .env.example .env.local
# Edit .env.local with your API URL and OAuth credentials

pnpm dev             # start dev server at http://localhost:3000
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_APP_URL` | Yes | `http://localhost:3000` | Frontend URL |
| `NEXTAUTH_URL` | Yes | `http://localhost:3000` | NextAuth callback URL |
| `NEXTAUTH_SECRET` | Yes | -- | 32+ char secret for JWT signing |
| `GITHUB_CLIENT_ID` | For GitHub login | -- | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | For GitHub login | -- | GitHub OAuth App secret |
| `GOOGLE_CLIENT_ID` | For Google login | -- | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | For Google login | -- | Google OAuth secret |

## Available Commands

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start development server (port 3000) |
| `pnpm build` | Production build |
| `pnpm start` | Start production server |
| `pnpm lint` | Run ESLint |
| `pnpm type-check` | Run TypeScript type checking |
| `pnpm format` | Format code with Prettier |
| `pnpm test` | Run Vitest unit tests |
| `pnpm test:e2e` | Run Playwright E2E tests |

## Project Structure

```
src/
  app/          ? Next.js App Router pages
  components/   ? Reusable UI components
  hooks/        ? React Query + custom hooks
  lib/          ? API client, utils, constants
  stores/       ? Zustand state stores
```

## Design System

- **Colors**: CSS custom properties in `globals.css` (light + dark)
- **Typography**: Inter (body) + JetBrains Mono (code)
- **Components**: shadcn/ui pattern with Radix UI primitives
- **Icons**: Lucide React

## Docker

```bash
docker build -t eidos-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://api:8000 eidos-frontend
```
