import createClient from "openapi-fetch";
import type { paths, operations } from "@types"; // from openapi-typescript

const client = createClient<paths>({
  baseUrl:
    import.meta.env.VITE_API_BASE_URL ?? "https://cvt-api.ucalgarybaja.ca",
});

// Types pulled straight from your schema:
export type RunBody = NonNullable<
  operations["run_run_post"]["requestBody"]
>["content"]["application/json"];
export type RunResponse =
  operations["run_run_post"]["responses"]["200"]["content"]["application/json"];

export async function runSimulation(body?: RunBody): Promise<RunResponse> {
  const { data, error } = await client.POST("/run", { body: body ?? {} });
  if (error) throw error;
  return data!;
}
