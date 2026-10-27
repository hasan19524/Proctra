/**
 * REST client for the Procto API (Phase 2).
 *
 * Same-origin only: requests go to `/api/v1/*`, which Next.js rewrites to the
 * backend, so the httpOnly refresh cookie (SameSite=Lax, path /api/v1/auth)
 * is always sent. The access token lives in module memory — never localStorage.
 */

export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  role: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RegisterInput {
  email: string;
  password: string;
  displayName: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthResponse> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return fallback;
  }
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return [String((item as { msg: unknown }).msg)];
        }
        return [];
      });
      if (messages.length > 0) {
        return messages.join(" ");
      }
    }
  }
  return fallback;
}

async function toApiError(response: Response): Promise<ApiError> {
  return new ApiError(response.status, await readErrorMessage(response));
}

/**
 * Exchange the refresh cookie for a fresh access token.
 * Concurrent callers share a single in-flight request.
 */
export function refreshSession(): Promise<AuthResponse> {
  if (!refreshInFlight) {
    refreshInFlight = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    })
      .then(async (response) => {
        if (!response.ok) {
          accessToken = null;
          throw await toApiError(response);
        }
        const auth = (await response.json()) as AuthResponse;
        accessToken = auth.access_token;
        return auth;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
}

/**
 * Perform a JSON request against the same-origin API.
 * On a 401 with a stored access token, refreshes once and retries.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;

  const send = (token: string | null): Promise<Response> =>
    fetch(path, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(auth && token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      credentials: "same-origin",
    });

  let response = await send(accessToken);

  if (response.status === 401 && auth && accessToken) {
    const refreshed = await refreshSession();
    response = await send(refreshed.access_token);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return null as T;
  }
  return (await response.json()) as T;
}

export const authApi = {
  async register(input: RegisterInput): Promise<AuthResponse> {
    const auth = await apiFetch<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body: {
        email: input.email,
        password: input.password,
        display_name: input.displayName,
      },
      auth: false,
    });
    accessToken = auth.access_token;
    return auth;
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const auth = await apiFetch<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    accessToken = auth.access_token;
    return auth;
  },

  async logout(): Promise<void> {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST", auth: false });
    } finally {
      accessToken = null;
    }
  },
};

export interface Meeting {
  id: string;
  code: string;
  title: string | null;
  host_id: string;
  status: "waiting" | "live" | "ended";
  is_locked: boolean;
  waiting_room: boolean;
  has_password: boolean;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

/** Ephemeral LiveKit (SFU) credentials for one meeting. */
export interface LiveKitCredentials {
  url: string;
  token: string;
}

export interface CreateMeetingOptions {
  title?: string;
  password?: string;
  waitingRoom?: boolean;
}

export const meetingsApi = {
  async create(titleOrOptions?: string | CreateMeetingOptions): Promise<Meeting> {
    let body: Record<string, unknown> = {};
    if (typeof titleOrOptions === "string") {
      if (titleOrOptions) body = { title: titleOrOptions };
    } else if (titleOrOptions) {
      if (titleOrOptions.title) body.title = titleOrOptions.title;
      if (titleOrOptions.password) body.password = titleOrOptions.password;
      if (titleOrOptions.waitingRoom) body.waiting_room = true;
    }
    return apiFetch<Meeting>("/api/v1/meetings", {
      method: "POST",
      body,
    });
  },

  async get(code: string): Promise<Meeting> {
    return apiFetch<Meeting>(`/api/v1/meetings/${encodeURIComponent(code.trim().toLowerCase())}`);
  },

  /** Mint SFU join credentials (server enforces lock/end/password/waiting before issuing). */
  async getToken(code: string, password?: string): Promise<LiveKitCredentials> {
    return apiFetch<LiveKitCredentials>(
      `/api/v1/meetings/${encodeURIComponent(code.trim().toLowerCase())}/token`,
      { method: "POST", body: password ? { password } : {} },
    );
  },
};

/** Extract a meet code from raw input (bare code or pasted link). */
export function extractMeetingCode(input: string): string | null {
  const match = input.match(/([a-z2-9]{3}-[a-z2-9]{3}-[a-z2-9]{3})/i);
  return match ? match[1].toLowerCase() : null;
}
