import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { request } from "./api/client";
import { tokens } from "./auth/tokens";
import { API, server } from "./test/server";
import { renderApp } from "./test/render";

describe("login", () => {
  it("signs a manager in and lands on the dashboard", async () => {
    const { user } = renderApp({ route: "/login" });

    await user.type(await screen.findByLabelText("Email"), "demo-manager-1@demo.seed");
    await user.type(screen.getByLabelText("Password"), "demopass123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText(/Demo Manager · manager/)).toBeInTheDocument();
    expect(tokens.refresh).toBe("refresh-manager");
  });

  it("shows a clear error for a wrong password and stays on the form", async () => {
    const { user } = renderApp({ route: "/login" });

    await user.type(await screen.findByLabelText("Email"), "demo-manager-1@demo.seed");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(tokens.refresh).toBeNull();
  });

  it("redirects signed-out visitors to the login form", async () => {
    renderApp({ route: "/products" });
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("restores the session after a reload using the stored refresh token", async () => {
    renderApp({ route: "/products", signedInAs: "employee" });
    expect(await screen.findByRole("heading", { level: 1, name: "Products" })).toBeInTheDocument();
  });
});

describe("logout", () => {
  it("blacklists the refresh token on the server and clears the session", async () => {
    let sent: unknown = null;
    server.use(
      http.post(`${API}/auth/logout`, async ({ request: req }) => {
        sent = await req.json();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderApp({ route: "/products", signedInAs: "manager" });

    await user.click(await screen.findByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(sent).toEqual({ refresh: "refresh-manager" });
    expect(tokens.refresh).toBeNull();
    expect(tokens.access).toBeNull();
  });
});

describe("token refresh", () => {
  it("refreshes once, retries the request, and shares one refresh between parallel 401s", async () => {
    tokens.set("expired", "refresh-manager");
    let refreshCalls = 0;
    server.use(
      http.post(`${API}/auth/refresh`, () => {
        refreshCalls++;
        return HttpResponse.json({ access: "fresh-access", refresh: "rotated-refresh" });
      }),
      http.get(`${API}/dashboard`, ({ request: req }) =>
        req.headers.get("Authorization") === "Bearer fresh-access" ? HttpResponse.json({ ok: true }) : HttpResponse.json({ detail: "expired" }, { status: 401 }),
      ),
    );

    const results = await Promise.all([request("/dashboard"), request("/dashboard"), request("/dashboard")]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1);
    expect(tokens.refresh).toBe("rotated-refresh");
  });

  it("signs the user out when the refresh token is rejected", async () => {
    server.use(
      http.post(`${API}/auth/refresh`, () => HttpResponse.json({ detail: "blacklisted" }, { status: 401 })),
      http.get(`${API}/dashboard`, () => HttpResponse.json({ detail: "expired" }, { status: 401 })),
    );
    renderApp({ route: "/dashboard", signedInAs: "manager" });

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(tokens.refresh).toBeNull());
  });
});
