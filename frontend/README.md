# CVT Simulator Frontend

React + TypeScript + Vite application for CVT simulation and visualization.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env and set VITE_API_BASE_URL to your backend URL
```

3. Start development server:
```bash
npm run dev
```

## API Types

The frontend uses auto-generated TypeScript types from the backend OpenAPI schema.

To regenerate types after backend changes:
```bash
# Make sure backend is running first
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

## Project Structure

- `src/types/` - TypeScript type definitions (centralized)
- `src/utils/` - Utility functions and API client
- `src/contexts/` - React contexts for global state
- `src/hooks/` - Custom React hooks
- `src/components/` - Reusable UI components
- `src/pages/` - Page-level components (routes)

## For Developers

See [AI_CONTEXT.md](./AI_CONTEXT.md) for detailed architecture documentation and coding practices.