export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: FieldErrors;

  constructor(status: number, message: string, fieldErrors: FieldErrors = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  /** The backend answers 409 for "already done" and "not enough stock". */
  get isConflict() {
    return this.status === 409;
  }
}

function toList(v: unknown): string[] {
  if (Array.isArray(v)) return v.flatMap(toList);
  if (v && typeof v === "object") return Object.values(v).flatMap(toList);
  return v == null ? [] : [String(v)];
}

/**
 * DRF answers errors in three shapes: {"detail": "..."}, a dict of field -> [messages]
 * (serializer validation, nested for line items), or a bare list. Flatten all of them.
 */
export function parseErrorBody(status: number, body: unknown): ApiError {
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return new ApiError(status, record.detail);
    const fieldErrors: FieldErrors = {};
    for (const [key, value] of Object.entries(record)) {
      const msgs = toList(value);
      if (msgs.length) fieldErrors[key] = msgs;
    }
    const all = Object.entries(fieldErrors).map(([k, v]) => `${k === "non_field_errors" ? "" : k + ": "}${v.join(" ")}`);
    if (all.length) return new ApiError(status, all.join(" "), fieldErrors);
  }
  if (Array.isArray(body)) {
    const msgs = toList(body);
    if (msgs.length) return new ApiError(status, msgs.join(" "));
  }
  if (status === 429) return new ApiError(status, "Too many requests. Wait a moment and try again.");
  if (status >= 500) return new ApiError(status, "The server hit an error. Try again in a moment.");
  return new ApiError(status, `Request failed (${status})`);
}
