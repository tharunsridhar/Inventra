import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useProductName } from "../api/hooks";
import { api } from "../api/resources";
import type { ReportKind } from "../api/types";
import { Badge } from "../components/Badge";
import { SelectField, TextField } from "../components/Fields";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/StateViews";
import { dateTime, money } from "../format";

const ROW_LIMIT = 100;

interface Params {
  kind: ReportKind;
  start: string;
  end: string;
}

export function ReportsPage() {
  const [form, setForm] = useState<Params>({ kind: "products", start: "", end: "" });
  const [submitted, setSubmitted] = useState<Params | null>(null);

  function run(e: FormEvent) {
    e.preventDefault();
    setSubmitted({ ...form });
  }

  return (
    <>
      <PageHeader title="Reports" />
      <section className="panel" aria-label="Report builder">
        <form className="toolbar" onSubmit={run}>
          <SelectField label="Report" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ReportKind })}>
            <option value="products">Products</option>
            <option value="purchases">Purchases</option>
            <option value="sales">Sales</option>
            <option value="inventory">Inventory movements</option>
          </SelectField>
          <TextField label="From" type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
          <TextField label="To" type="date" value={form.end} min={form.start || undefined} onChange={(e) => setForm({ ...form, end: e.target.value })} />
          <button type="submit" className="btn btn-primary">Run report</button>
        </form>
        <div className="panel-body">
          {submitted ? <ReportResult params={submitted} /> : <div className="state state-empty">Choose a report and press Run report.</div>}
        </div>
      </section>
    </>
  );
}

function ReportResult({ params }: { params: Params }) {
  const query = useQuery({
    queryKey: ["report", params],
    queryFn: () =>
      api.report(params.kind, {
        start_date: params.start ? `${params.start}T00:00:00` : undefined,
        end_date: params.end ? `${params.end}T23:59:59` : undefined,
      }),
  });
  const productName = useProductName();

  return (
    <div aria-live="polite">
      <QueryBoundary query={query}>
        {(data) => {
          if ("summary" in data) {
            const rows = data.transactions.slice(0, ROW_LIMIT);
            return (
              <>
                <Stats items={[["Purchased", data.summary.total_purchased], ["Sold", data.summary.total_sold], ["Returned", data.summary.total_returned], ["Damaged", data.summary.total_damaged]]} />
                <Table caption="Inventory movements" head={["Product", "Type", "Qty", "Reason", "When"]} empty="No movements in this range." total={data.transactions.length}>
                  {rows.map((t) => (
                    <tr key={t.id}><td>{productName(t.product_id)}</td><td><Badge>{t.transaction_type}</Badge></td><td>{t.quantity}</td><td className="muted">{t.reason || "—"}</td><td className="muted">{dateTime(t.created_at)}</td></tr>
                  ))}
                </Table>
              </>
            );
          }
          if ("total_revenue" in data) {
            return (
              <>
                <Stats items={[["Orders", data.total_orders], ["Revenue", money(data.total_revenue)]]} />
                <Table caption="Sales" head={["Invoice", "Status", "Total", "Created"]} empty="No sales in this range." total={data.items.length}>
                  {data.items.slice(0, ROW_LIMIT).map((s) => (
                    <tr key={s.id}><td className="mono">{s.invoice_number || "—"}</td><td><Badge>{s.status}</Badge></td><td>{money(s.total_amount)}</td><td className="muted">{dateTime(s.created_at)}</td></tr>
                  ))}
                </Table>
              </>
            );
          }
          if ("total_cost" in data) {
            return (
              <>
                <Stats items={[["Orders", data.total_orders], ["Total cost", money(data.total_cost)]]} />
                <Table caption="Purchases" head={["Order", "Status", "Cost", "Created"]} empty="No purchases in this range." total={data.items.length}>
                  {data.items.slice(0, ROW_LIMIT).map((p) => (
                    <tr key={p.id}><td className="mono">{p.id.slice(0, 8)}…</td><td><Badge>{p.status}</Badge></td><td>{money(p.total_cost)}</td><td className="muted">{dateTime(p.created_at)}</td></tr>
                  ))}
                </Table>
              </>
            );
          }
          return (
            <>
              <Stats items={[["Products", data.total_count]]} />
              <Table caption="Products" head={["SKU", "Name", "Cost", "Price", "Stock"]} empty="No products in this range." total={data.items.length}>
                {data.items.slice(0, ROW_LIMIT).map((p) => (
                  <tr key={p.id}><td className="mono">{p.sku}</td><td>{p.name}</td><td>{money(p.cost_price)}</td><td>{money(p.selling_price)}</td><td>{p.current_stock}</td></tr>
                ))}
              </Table>
            </>
          );
        }}
      </QueryBoundary>
    </div>
  );
}

function Stats({ items }: { items: Array<[string, string | number]> }) {
  return (
    <dl className="stat-grid">
      {items.map(([label, value]) => (
        <div key={label} className="stat-card"><dt>{label}</dt><dd>{typeof value === "number" ? value.toLocaleString("en-IN") : value}</dd></div>
      ))}
    </dl>
  );
}

function Table({ caption, head, total, empty, children }: { caption: string; head: string[]; total: number; empty: string; children: React.ReactNode }) {
  if (total === 0) return <div className="state state-empty">{empty}</div>;
  return (
    <>
      <div className="table-wrap">
        <table>
          <caption className="sr-only">{caption}</caption>
          <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{children}</tbody>
        </table>
      </div>
      {total > ROW_LIMIT && <p className="muted">Showing the first {ROW_LIMIT} of {total} rows.</p>}
    </>
  );
}
