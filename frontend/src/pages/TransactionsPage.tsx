import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useProductName } from "../api/hooks";
import { api } from "../api/resources";
import { Badge } from "../components/Badge";
import { SelectField } from "../components/Fields";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { QueryBoundary } from "../components/StateViews";
import { dateTime } from "../format";

const PAGE_SIZE = 15;

/** The stock ledger. Read-only: the API exposes no create, update or delete route for it. */
export function TransactionsPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const type = params.get("type") ?? "";
  const productName = useProductName();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const ledger = useQuery({
    queryKey: ["ledger", { page, type }],
    queryFn: () => api.ledger({ page, page_size: PAGE_SIZE, transaction_type: type, ordering: "-created_at" }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader title="Transactions" />
      <section className="panel" aria-label="Stock ledger">
        <div className="toolbar">
          <SelectField label="Type" value={type} onChange={(e) => setParam("type", e.target.value)}>
            <option value="">All types</option>
            <option value="purchase">Purchase</option>
            <option value="sale">Sale</option>
            <option value="return">Return</option>
            <option value="damage">Damage</option>
          </SelectField>
          <p className="muted toolbar-note">Append-only ledger. Entries cannot be edited or deleted.</p>
        </div>
        <div className="panel-body">
          <QueryBoundary query={ledger} isEmpty={(d) => d.results.length === 0} empty="No transactions match this filter.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Inventory transactions</caption>
                    <thead><tr><th scope="col">Product</th><th scope="col">Type</th><th scope="col">Qty</th><th scope="col">Reason</th><th scope="col">When</th></tr></thead>
                    <tbody>
                      {data.results.map((t) => (
                        <tr key={t.id}>
                          <td>{productName(t.product)}</td>
                          <td><Badge>{t.transaction_type}</Badge></td>
                          <td>{t.quantity}</td>
                          <td className="muted">{t.reason || "—"}</td>
                          <td className="muted">{dateTime(t.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={page} pageSize={PAGE_SIZE} count={data.count} onPage={(n) => setParam("page", String(n))} />
              </>
            )}
          </QueryBoundary>
        </div>
      </section>
    </>
  );
}
