import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import { tokens } from "../auth/tokens";
import { ToastProvider } from "../components/Toasts";

/** Renders the whole app. Pass `signedInAs` to start with a stored refresh token (a reload). */
export function renderApp({ route = "/", signedInAs }: { route?: string; signedInAs?: "admin" | "manager" | "employee" } = {}) {
  if (signedInAs) tokens.set(`access-${signedInAs}`, `refresh-${signedInAs}`);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const user = userEvent.setup();
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { user, queryClient, ...utils };
}
