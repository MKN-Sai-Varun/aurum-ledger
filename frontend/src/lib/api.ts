export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function messageFrom(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Please check the values you entered.";
  }
  return status >= 500
    ? "Something went wrong on the server. Try again."
    : "The request couldn't be completed.";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const headers: Record<string, string> = { ...extraHeaders };
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body:
        body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  if (response.status === 204) return undefined as T;

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const isAuthCall = path === "/api/auth/login" || path === "/api/auth/me";
    if (response.status === 401 && !isAuthCall) onUnauthorized?.();
    throw new ApiError(response.status, messageFrom(data, response.status));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>("POST", path, body, headers),
  postForm: <T>(path: string, form: FormData) => request<T>("POST", path, form),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
};

/** The message for a failed save. If the outcome is unknown, say so. */
export function saveErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const unknown = error.status === 0 || error.status === 502 || error.status === 504;
    return unknown
      ? `${error.message} The entry may already have been saved. Press Save again to retry safely, or check the ledger before changing anything.`
      : error.message;
  }
  return "Something went wrong. Try again.";
}