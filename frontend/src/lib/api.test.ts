import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiFetch,
  authApi,
  clearAccessToken,
  getAccessToken,
  refreshSession,
  type AuthResponse,
} from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function authFixture(token = "access-1"): AuthResponse {
  return {
    access_token: token,
    token_type: "bearer",
    expires_in: 900,
    user: {
      id: "u-1",
      email: "hasan@example.com",
      display_name: "Hasan",
      avatar_url: null,
      role: "user",
      created_at: "2026-10-03T00:00:00Z",
    },
  };
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  clearAccessToken();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authApi.login", () => {
  it("posts credentials without an auth header and stores the access token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture()));

    const auth = await authApi.login("hasan@example.com", "password123");

    expect(auth.user.display_name).toBe("Hasan");
    expect(getAccessToken()).toBe("access-1");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(init?.headers).not.toHaveProperty("Authorization");
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "hasan@example.com",
      password: "password123",
    });
  });

  it("throws ApiError with the backend message on failure and never refreshes", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid email or password" }));

    const error = await authApi.login("hasan@example.com", "wrong").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).message).toBe("Invalid email or password");
    expect(getAccessToken()).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("apiFetch auth handling", () => {
  it("attaches the bearer token when one is stored", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture()));
    await authApi.login("hasan@example.com", "password123");

    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "u-1" }));
    await apiFetch("/api/v1/auth/me");

    const [, init] = fetchMock.mock.calls[1] ?? [];
    expect(init?.headers).toMatchObject({ Authorization: "Bearer access-1" });
  });

  it("fails fast with 401 when no token is stored", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated" }));

    const error = await apiFetch("/api/v1/auth/me").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture("access-1")));
    await authApi.login("hasan@example.com", "password123");

    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated" }))
      .mockResolvedValueOnce(jsonResponse(200, authFixture("access-2")))
      .mockResolvedValueOnce(jsonResponse(200, { id: "u-1" }));

    const me = await apiFetch<{ id: string }>("/api/v1/auth/me");

    expect(me.id).toBe("u-1");
    expect(getAccessToken()).toBe("access-2");
    expect(fetchMock).toHaveBeenCalledTimes(4);

    const [, retryInit] = fetchMock.mock.calls[3] ?? [];
    expect(retryInit?.headers).toMatchObject({ Authorization: "Bearer access-2" });
  });

  it("clears the token and throws when the refresh fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture("access-1")));
    await authApi.login("hasan@example.com", "password123");

    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated" }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated" }));

    const error = await apiFetch("/api/v1/auth/me").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(getAccessToken()).toBeNull();
  });

  it("shares a single refresh across parallel 401s", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture("access-1")));
    await authApi.login("hasan@example.com", "password123");

    let meCalls = 0;
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/v1/auth/me") {
        meCalls += 1;
        if (meCalls <= 2) {
          return jsonResponse(401, { detail: "Not authenticated" });
        }
        return jsonResponse(200, { id: "u-1" });
      }
      if (url === "/api/v1/auth/refresh") {
        return jsonResponse(200, authFixture("access-2"));
      }
      if (url === "/api/v1/auth/login") {
        return jsonResponse(200, authFixture("access-1"));
      }
      return jsonResponse(500, { detail: "unexpected" });
    });

    const [a, b] = await Promise.all([
      apiFetch<{ id: string }>("/api/v1/auth/me"),
      apiFetch<{ id: string }>("/api/v1/auth/me"),
    ]);

    expect(a.id).toBe("u-1");
    expect(b.id).toBe("u-1");

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/refresh"));
    expect(refreshCalls).toHaveLength(1);
  });
});

describe("refreshSession", () => {
  it("collapses concurrent callers into one request", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, authFixture("access-9")));

    const [first, second] = await Promise.all([refreshSession(), refreshSession()]);

    expect(first.access_token).toBe("access-9");
    expect(second.access_token).toBe("access-9");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBe("access-9");
  });

  it("parses pydantic 422 detail arrays into a readable message", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(422, {
        detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }],
      }),
    );

    const error = await refreshSession().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("value is not a valid email address");
  });
});
