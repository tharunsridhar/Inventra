import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { tokens } from "../auth/tokens";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  tokens.clear();
  localStorage.clear();
});
afterAll(() => server.close());
