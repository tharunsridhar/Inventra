import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/resources";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/StateViews";

export function DashboardPage() {
  const stats = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const lowStock = useQuery({
    queryKey: ["products", "low-stock-list"],
    queryFn: () => api.products({ stock_status: "low_stock", ordering: "current_stock", page_size: 8 }),
  });

  return (
    <>
      <PageHeader title="Dashboard" />
      <QueryBoundary query={stats}>
        {(d) => {
          const cards: Array<[string, number, string]> = [
            ["Products", d.total_products, ""],
            ["Categories", d.total_categories, ""],
            ["Suppliers", d.total_suppliers, ""],
            ["Users", d.total_users, ""],
            ["Purchase orders", d.total_purchases, ""],
            ["Sales orders", d.total_sales, ""],
            ["Low stock", d.low_stock_products, "warn"],
            ["Out of stock", d.out_of_stock_products, "danger"],
          ];
          return (
            <dl className="stat-grid">
              {cards.map(([label, value, tone]) => (
                <div key={label} className={`stat-card ${tone}`}>
                  <dt>{label}</dt>
                  <dd>{value.toLocaleString("en-IN")}</dd>
                </div>
              ))}
            </dl>
          );
        }}
      </QueryBoundary>

      <section className="panel" aria-labelledby="low-stock-title">
        <div className="panel-header">
          <h2 id="low-stock-title">Low stock</h2>
          <Link to="/products?stock=low_stock">See all low stock</Link>
        </div>
        <div className="panel-body">
          <QueryBoundary query={lowStock} isEmpty={(d) => d.results.length === 0} empty="Nothing is running low. Nice.">
            {(page) => (
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Products at or below their low-stock threshold</caption>
                  <thead>
                    <tr>
                      <th scope="col">SKU</th>
                      <th scope="col">Name</th>
                      <th scope="col">Stock</th>
                      <th scope="col">Threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.results.map((p) => (
                      <tr key={p.id}>
                        <td className="mono">{p.sku}</td>
                        <td>{p.name}</td>
                        <td>{p.current_stock}</td>
                        <td>{p.low_stock_threshold}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryBoundary>
        </div>
      </section>
    </>
  );
}
