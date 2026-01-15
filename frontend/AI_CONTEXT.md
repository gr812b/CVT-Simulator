# Frontend Architecture Guide for AI Models

This document provides context for AI coding assistants working on this codebase. It explains where things are, how they work together, and what practices to follow.

## Type System Architecture

### Auto-Generated API Types (`src/types/api.ts`)
**NEVER EDIT THIS FILE MANUALLY** - It's generated from the backend OpenAPI schema.

To regenerate after backend changes:
```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

This file contains:
- All API endpoint types (`paths` and `operations`)
- All backend model schemas (`components['schemas']`)
- Request/response body types for every endpoint

**Usage pattern:**
```typescript
import type { components, operations } from '@types';

// For API request/response types
type RequestBody = operations['endpoint_name']['requestBody']['content']['application/json'];
type ResponseBody = operations['endpoint_name']['responses']['200']['content']['application/json'];

// For backend model types
type BackendModel = components['schemas']['ModelName'];
```

### Centralized Parameter Types (`src/types/parameter.ts`)
This is the **single source of truth** for all simulation parameters.

**Key exports:**
- `Parameter` - Union of all parameter names (e.g., `'FlyweightMass' | 'VehicleWeight' | ...`)
- `ParameterValue` - Union of all possible value types: `string | number | boolean | PiecewiseRampConfig | null`
- `PiecewiseRampConfig` - Type alias for `components['schemas']['PiecewiseRampConfigModel']`
- `ParameterState` - Record mapping each Parameter to its value
- `PARAMETERS` - Configuration object with validation, defaults, units, descriptions for each parameter

**Always import from `@types`:**
```typescript
import { Parameter, ParameterValue, PiecewiseRampConfig, ParameterState } from '@types';
```

### Type Barrel Export (`src/types/index.ts`)
All types are re-exported through this barrel file. Always import from `@types`:
```typescript
import type { Parameter, ParameterState, components } from '@types';
```

## Critical Rules

### ✅ DO
- Import all types from `@types` (never local definitions)
- Use `ParameterValue` for any code handling parameter values
- Use `PiecewiseRampConfig` for ramp configuration objects  
- Extract API types from `operations` and `components['schemas']`
- Follow existing patterns when adding new endpoints/parameters
- Regenerate `api.ts` after any backend schema changes

### ❌ DON'T
- Use `any` type (find or create proper types instead)
- Redefine types that already exist in `@types`
- Manually edit `src/types/api.ts`
- Create local type aliases for centralized types
- Use `as any` casts (use proper type assertions)

## API Client Pattern (`src/utils/api.ts`)

All API calls go through typed functions using `openapi-fetch`:

```typescript
import createClient from 'openapi-fetch';
import type { paths, operations } from '@types';

const client = createClient<paths>({ 
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000' 
});

// Extract types from auto-generated schema
export type EndpointRequestBody = NonNullable<
  operations['endpoint_operation_id']['requestBody']
>['content']['application/json'];

export type EndpointResponse = 
  operations['endpoint_operation_id']['responses']['200']['content']['application/json'];

// Create typed function
export async function callEndpoint(body: EndpointRequestBody): Promise<EndpointResponse> {
  const { data, error } = await client.POST('/endpoint', { body });
  if (error) throw error;
  return data!;
}
```

**Benefits:**
- Full type safety and IntelliSense
- Automatic request/response validation
- Centralized error handling
- Uses environment variable for base URL

## Key Utilities

### `src/utils/parameterMapping.ts`
Maps frontend `ParameterState` (PascalCase) to backend API format (snake_case):
```typescript
export const mapParametersToApiBody = (parameters: ParameterState): RunBody => {
  return {
    flyweight_mass: parameters.FlyweightMass,
    primary_ramp_config: parameters.PrimaryRampConfig,
    // ... all parameters
  };
};
```
**Always use this** when calling the simulation endpoint.

### `src/utils/validation.ts`
Input validators for parameters. Used in `PARAMETERS` config.

### `src/utils/unitConversion.ts`
Converts simulation results between unit systems (SI, Imperial, etc.).

### `src/utils/graph.ts`
Helper functions for graph data processing and visualization.

## State Management

### Global Contexts (`src/contexts/`)

**ParameterContext** - Simulation parameters
```typescript
const { parameters, setParameter, setMultipleParameters } = useParameter();
// parameters type: ParameterState
```

**LoadingContext** - Loading state with messages
```typescript
const { isLoading, loadingMessage, setLoading } = useLoading();
```

**ThemeContext** - Theme switching (light/dark)

### Form State Hook (`src/hooks/useFormState.ts`)
Manages form state with validation and change tracking:
```typescript
const formState = useFormState(initialParameters);
// formState.values: Record<Parameter, ParameterValue>
// formState.updateField: (parameter: Parameter, value: ParameterValue) => void
```

**Key features:**
- Type-safe parameter updates
- Validation with error tracking
- Dirty state detection
- Parse values for API submission

## Common Patterns

### Adding a New Parameter
1. Add to `Parameter` union in `src/types/parameter.ts`
2. Add configuration to `PARAMETERS` object (validation, default, units, etc.)
3. Add to `ParameterState` type definition
4. Update `mapParametersToApiBody` in `src/utils/parameterMapping.ts`
5. Ensure backend has matching field in `SimulationArgs`

### Adding a New API Endpoint
1. Define endpoint in backend FastAPI with response model
2. Regenerate frontend types: `npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts`
3. Add typed function to `src/utils/api.ts`:
   ```typescript
   export type NewEndpointBody = /* extract from operations */;
   export type NewEndpointResponse = /* extract from operations */;
   export async function callNewEndpoint(body: NewEndpointBody): Promise<NewEndpointResponse> {
     const { data, error } = await client.POST('/new-endpoint', { body });
     if (error) throw error;
     return data!;
   }
   ```
4. Use in components/hooks

### Handling Nested Types (e.g., Ramp Configs)
When backend expects nested dataclass objects:

**Frontend side:**
- Use auto-generated types: `PiecewiseRampConfig` = `components['schemas']['PiecewiseRampConfigModel']`
- Pass as plain object (JavaScript object matching the schema shape)

**Backend side:**
- In `SimulationArgs.from_mapping()`, detect dict values for nested fields
- Convert using `.from_dict()` method on the dataclass:
  ```python
  if key in ("primary_ramp_config", "secondary_ramp_config") and isinstance(v, dict):
      overrides[key] = PiecewiseRampConfig.from_dict(v)
  ```

This maintains clean serialization: Frontend object → API JSON → Backend dataclass

## File Organization

```
src/
├── types/          # All type definitions (import from @types)
│   ├── api.ts      # Auto-generated (don't edit)
│   ├── parameter.ts # Parameter definitions (single source of truth)
│   ├── graph.ts    # Graph-related types
│   └── index.ts    # Barrel export
├── utils/          # Pure functions and API client
│   ├── api.ts      # Typed API functions
│   ├── parameterMapping.ts
│   ├── validation.ts
│   ├── unitConversion.ts
│   └── graph.ts
├── contexts/       # React contexts (global state)
├── hooks/          # Custom React hooks
├── components/     # Reusable UI components
├── pages/          # Route-level components
├── assets/         # Static files
└── styles/         # Global styles
```

## Environment Setup

Create `.env` file (copy from `.env.example`):
```
VITE_API_BASE_URL=http://localhost:8000
```
In GitHub Codespaces, use the forwarded URL (e.g., `https://*-8000.app.github.dev/`)

## Quick Reference for Common Tasks

**Need parameter validation?** → Check `src/utils/validation.ts`  
**Need to call API?** → Add function to `src/utils/api.ts` using existing patterns  
**Need parameter type?** → Import `Parameter`, `ParameterValue`, `ParameterState` from `@types`  
**Need backend model type?** → Import `components` from `@types`, use `components['schemas']['ModelName']`  
**Backend changed?** → Regenerate `src/types/api.ts`  
**Adding parameter?** → Update `src/types/parameter.ts` AND `src/utils/parameterMapping.ts`

## Type Safety Checklist
- [ ] No `any` types used
- [ ] Types imported from `@types` (not redefined locally)
- [ ] API functions use types from `operations`
- [ ] Backend models use types from `components['schemas']`
- [ ] Parameter-related code uses `Parameter`, `ParameterValue`, `ParameterState`
- [ ] Ramp configs use `PiecewiseRampConfig` type
