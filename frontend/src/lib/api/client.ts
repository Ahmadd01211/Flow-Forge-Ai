export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") {
    const csrf = await fetch("/api/v1/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!csrf.ok)
      throw new ApiError(
        "Unable to establish a secure request. Please reload.",
        csrf.status,
      );
    headers.set("X-CSRF-Token", (await csrf.json()).csrf_token);
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const details = body.error?.details
      ?.map(
        (d: { path: string; message: string }) =>
          `${d.path.replace("body.", "")}: ${d.message}`,
      )
      .join(" · ");
    throw new ApiError(
      details ||
        body.error?.message ||
        "The request could not be completed. Please try again.",
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
