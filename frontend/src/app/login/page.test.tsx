// @vitest-environment jsdom
import * as React from "react";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ApiError } from "@/lib/api";

const { loginMock, replaceMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: function LinkMock({
    href,
    children,
    ...rest
  }: React.ComponentProps<"a"> & { href: string }) {
    return (
      <a href={href} {...rest}>
        {children}
      </a>
    );
  },
}));

vi.mock("@/components/auth/session-context", () => ({
  useSession: () => ({
    status: "unauthenticated",
    user: null,
    login: loginMock,
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

import LoginPage from "./page";

beforeEach(() => {
  loginMock.mockReset();
  replaceMock.mockReset();
});

afterEach(cleanup);

function fillAndSubmit(fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("LoginPage", () => {
  it("shows field errors and does not call the API when inputs are empty", async () => {
    render(<LoginPage />);
    fillAndSubmit({});

    expect(await screen.findByText("Enter your email.")).toBeTruthy();
    expect(screen.getByText("Enter your password.")).toBeTruthy();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("rejects malformed email addresses client-side", async () => {
    render(<LoginPage />);
    fillAndSubmit({ Email: "not-an-email", Password: "secret123" });

    expect(await screen.findByText("Enter a valid email address.")).toBeTruthy();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("surfaces the backend error message on failed sign-in", async () => {
    loginMock.mockRejectedValue(new ApiError(401, "Invalid email or password"));

    render(<LoginPage />);
    fillAndSubmit({ Email: "hasan@example.com", Password: "wrong-pass" });

    expect(await screen.findByText("Invalid email or password")).toBeTruthy();
    expect(loginMock).toHaveBeenCalledWith("hasan@example.com", "wrong-pass");
    expect(replaceMock).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("navigates to the home page after a successful sign-in", async () => {
    loginMock.mockResolvedValue({ access_token: "t", user: { id: "u1" } });

    render(<LoginPage />);
    fillAndSubmit({ Email: "hasan@example.com", Password: "password123" });

    await vi.waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith("hasan@example.com", "password123");
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("disables the submit button while the request is pending", async () => {
    let resolveLogin: (value: unknown) => void = () => {};
    loginMock.mockImplementation(() => new Promise((resolve) => (resolveLogin = resolve)));

    render(<LoginPage />);
    fillAndSubmit({ Email: "hasan@example.com", Password: "password123" });

    const button = await screen.findByRole("button", { name: /sign in/i });
    expect((button as HTMLButtonElement).disabled).toBe(true);

    resolveLogin({ access_token: "t", user: { id: "u1" } });
    await vi.waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
  });
});
