// @vitest-environment jsdom
import * as React from "react";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ApiError } from "@/lib/api";

const { registerMock, replaceMock } = vi.hoisted(() => ({
  registerMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
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
    login: vi.fn(),
    register: registerMock,
    logout: vi.fn(),
  }),
}));

import RegisterPage from "./page";

beforeEach(() => {
  registerMock.mockReset();
  replaceMock.mockReset();
});

afterEach(cleanup);

function fillAndSubmit(fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: /create account/i }));
}

describe("RegisterPage", () => {
  it("enforces the 8 character password minimum client-side", async () => {
    render(<RegisterPage />);
    fillAndSubmit({ Name: "Hasan", Email: "hasan@example.com", Password: "short" });

    expect(await screen.findByText("Password must be at least 8 characters.")).toBeTruthy();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("shows the backend message when the email is already registered", async () => {
    registerMock.mockRejectedValue(new ApiError(409, "Email already registered"));

    render(<RegisterPage />);
    fillAndSubmit({ Name: "Hasan", Email: "hasan@example.com", Password: "password123" });

    expect(await screen.findByText("Email already registered")).toBeTruthy();
    expect(registerMock).toHaveBeenCalledWith({
      email: "hasan@example.com",
      password: "password123",
      displayName: "Hasan",
    });
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("navigates to the home page after successful registration", async () => {
    registerMock.mockResolvedValue({ access_token: "t", user: { id: "u1" } });

    render(<RegisterPage />);
    fillAndSubmit({ Name: "Hasan Raza", Email: "hasan@example.com", Password: "password123" });

    await vi.waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({
        email: "hasan@example.com",
        password: "password123",
        displayName: "Hasan Raza",
      });
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });
});
