import { screen, within } from "@testing-library/react";
import { renderApp } from "./test/render";

const navLabels = () => within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link").map((a) => a.textContent);

describe("role-based navigation", () => {
  it("shows an employee only the pages the API lets them use", async () => {
    renderApp({ route: "/products", signedInAs: "employee" });
    await screen.findByRole("heading", { level: 1, name: "Products" });

    expect(navLabels()).toEqual(["Products", "Categories & suppliers", "Sales orders"]);
  });

  it("hides Users from a manager but keeps the staff pages", async () => {
    renderApp({ route: "/dashboard", signedInAs: "manager" });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });

    const labels = navLabels();
    expect(labels).toEqual(
      expect.arrayContaining(["Dashboard", "Purchase orders", "Returns", "Damage write-off", "Transactions", "Reports"]),
    );
    expect(labels).not.toContain("Users");
  });

  it("shows an admin every page", async () => {
    renderApp({ route: "/dashboard", signedInAs: "admin" });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });

    expect(navLabels()).toHaveLength(10);
    expect(navLabels()).toContain("Users");
  });

  it("blocks an employee who types a staff-only URL", async () => {
    renderApp({ route: "/returns", signedInAs: "employee" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Not available for your role");
    expect(screen.queryByRole("heading", { level: 1, name: "Returns" })).not.toBeInTheDocument();
  });

  it("sends an employee from the home route to Products, not the manager-only dashboard", async () => {
    renderApp({ route: "/", signedInAs: "employee" });
    expect(await screen.findByRole("heading", { level: 1, name: "Products" })).toBeInTheDocument();
  });
});
