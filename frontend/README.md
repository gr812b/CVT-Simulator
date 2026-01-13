

## API

Copy the .env.example and rename to .env, then replace the `VITE_API_BASE_URL` with the url of your backend. Default is `localhost:8000`, though in a github workspace it might be different.

To generate types from the API, make sure the API is running and run
`npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts`