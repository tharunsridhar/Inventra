import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { API, page, server, widget } from "./test/server";
import { renderApp } from "./test/render";

const createdOrder = {
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

describe("creating a sale", () => {
  it("sends the line items to the API and confirms with a toast", async () => {
    let posted: unknown = null;
    server.use(
      http.post(`${API}/sales-orders/`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(createdOrder, { status: 201 });
      }),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "+ New sale" }));
    const dialog = await screen.findByRole("dialog", { name: "New sale" });

    await user.type(within(dialog).getByLabelText("Customer name"), "Acme Ltd");
    await within(dialog).findByRole("option", { name: /Widget \(WID-001\)/ });
    await user.selectOptions(within(dialog).getByLabelText("Product 1"), widget.id);
    await user.clear(within(dialog).getByLabelText("Quantity 1"));
    await user.type(within(dialog).getByLabelText("Quantity 1"), "3");
    await user.click(within(dialog).getByRole("button", { name: "Create sale" }));

    await waitFor(() => expect(posted).toEqual({ customer_name: "Acme Ltd", customer_phone: null, items: [{ product_id: widget.id, quantity: 3 }] }));
    expect(await screen.findByText("Sales order created")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("asks for a product before submitting and does not call the API", async () => {
    let calls = 0;
    server.use(http.post(`${API}/sales-orders/`, () => { calls++; return HttpResponse.json(createdOrder, { status: 201 }); }));
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "+ New sale" }));
    const dialog = await screen.findByRole("dialog", { name: "New sale" });
    await user.click(within(dialog).getByRole("button", { name: "Create sale" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Choose a product for item 1.");
    expect(calls).toBe(0);
  });

  it("shows the API's validation message when it rejects the sale", async () => {
    server.use(
      http.post(`${API}/sales-orders/`, () => HttpResponse.json({ items: [{ product_id: ["Product(s) not found or inactive"] }] }, { status: 400 })),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "+ New sale" }));
    const dialog = await screen.findByRole("dialog", { name: "New sale" });
    await within(dialog).findByRole("option", { name: /Widget/ });
    await user.selectOptions(within(dialog).getByLabelText("Product 1"), widget.id);
    await user.click(within(dialog).getByRole("button", { name: "Create sale" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Product(s) not found or inactive");
  });
});

describe("completing a sale", () => {
  it("deducts stock after the confirm dialog and shows a success toast", async () => {
    server.use(
      http.get(`${API}/sales-orders/`, () => HttpResponse.json(page([createdOrder]))),
      http.post(`${API}/sales-orders/${createdOrder.id}/complete/`, () =>
        HttpResponse.json({ ...createdOrder, status: "completed", invoice_number: "INV-ABC123" }),
      ),
    );
    const { user } = renderApp({ route: "/sales-orders", signedInAs: "employee" });

    await user.click(await screen.findByRole("button", { name: "Complete sale for Acme Ltd" }));
    const dialog = await screen.findByRole("dialog", { name: "Complete sale" });
    expect(dialog).toHaveTextContent("Stock will be deducted");
    await user.click(within(dialog).getByRole("button", { name: "Complete sale" }));

    expect(await screen.findByText("Sale completed")).toBeInTheDocument();
  });
});
