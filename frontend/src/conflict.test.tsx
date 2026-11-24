import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { API, page, server, widget } from "./test/server";
import { renderApp } from "./test/render";

const order = {
  id: "22222222-2222-4222-8222-222222222222",
  status: "created",
  customer_name: "Acme Ltd",
  customer_phone: null,
  invoice_number: null,
  invoiced_at: null,
  items: [{ id: "i-1", product: widget.id, quantity: 3, unit_price: "100.00" }],
  created_by: "u-emp",
  created_at: "2026-11-01T10:00:00Z",
};

describe("409 on a retried completion", () => {
  it("shows the backend's message as a conflict, not a generic error, and refreshes the list", async () => {
    let listCalls = 0;
    server.use(
      http.get(`${API}/sales-orders/`, () => {
        listCalls++;
        // After the conflict the refetch shows the order as completed, which is its real state.
        return HttpResponse.json(page([listCalls === 1 ? order : { ...order, status: "completed", invoice_number: "INV-RETRY1" }]));
      }),
      http.post(`${API}/sales-orders/${order.id}/complete/`, () =>
        HttpResponse.json({ detail: "Sales order has already been completed" }, { status: 409 }),
      ),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "Complete sale for Acme Ltd" }));
    const dialog = await screen.findByRole("dialog", { name: "Complete sale" });
    await user.click(within(dialog).getByRole("button", { name: "Complete sale" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Conflict (409): nothing was changed.");
    expect(alert).toHaveTextContent("Sales order has already been completed");
    expect(alert).not.toHaveTextContent("Something went wrong");
    // The confirm button is gone so the retry cannot be fired a third time.
    expect(within(dialog).queryByRole("button", { name: "Complete sale" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();

    // The table behind the dialog was refetched and now shows the completed order.
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2));
    expect(await screen.findByText("INV-RETRY1")).toBeInTheDocument();
  });

  it("shows the insufficient-stock 409 with the server's numbers", async () => {
    server.use(
      http.get(`${API}/sales-orders/`, () => HttpResponse.json(page([order]))),
      http.post(`${API}/sales-orders/${order.id}/complete/`, () =>
        HttpResponse.json({ detail: "Insufficient stock for 'Widget': available 1, requested 3" }, { status: 409 }),
      ),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "Complete sale for Acme Ltd" }));
    const dialog = await screen.findByRole("dialog", { name: "Complete sale" });
    await user.click(within(dialog).getByRole("button", { name: "Complete sale" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Insufficient stock for 'Widget': available 1, requested 3");
  });

  it("keeps non-409 failures as a plain error so the user can retry", async () => {
    server.use(
      http.get(`${API}/sales-orders/`, () => HttpResponse.json(page([order]))),
      http.post(`${API}/sales-orders/${order.id}/complete/`, () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "Complete sale for Acme Ltd" }));
    const dialog = await screen.findByRole("dialog", { name: "Complete sale" });
    await user.click(within(dialog).getByRole("button", { name: "Complete sale" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).not.toHaveTextContent("Conflict");
    expect(within(dialog).getByRole("button", { name: "Complete sale" })).toBeEnabled();
  });
});
