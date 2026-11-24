import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface Shared {
  label: string;
  error?: string;
  hint?: string;
}

function Wrapper({ id, label, error, hint, children }: Shared & { id: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && (
        <span id={`${id}-hint`} className="field-hint">
          {hint}
        </span>
      )}
      {error && (
        <span id={`${id}-error`} className="field-error">
          {error}
        </span>
      )}
    </div>
  );
}

const describedBy = (id: string, error?: string, hint?: string) => (error ? `${id}-error` : hint ? `${id}-hint` : undefined);

export function TextField({ label, error, hint, ...props }: Shared & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Wrapper id={id} label={label} error={error} hint={hint}>
      <input id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} {...props} />
    </Wrapper>
  );
}

export function SelectField({ label, error, hint, children, ...props }: Shared & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Wrapper id={id} label={label} error={error} hint={hint}>
      <select id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} {...props}>
        {children}
      </select>
    </Wrapper>
  );
}

export function TextAreaField({ label, error, hint, ...props }: Shared & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Wrapper id={id} label={label} error={error} hint={hint}>
      <textarea id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} {...props} />
    </Wrapper>
  );
}

/** Form-level error from the API (field errors are shown beside their inputs). */
export function FormError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div role="alert" className="notice notice-error">
      {error.message}
    </div>
  );
}
