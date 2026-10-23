"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { readFields, writeFields, type SchemaField } from "./schema-fields";

function StringChoices({
  values,
  disabled,
  onChange,
}: {
  values?: unknown[];
  disabled: boolean;
  onChange: (values?: unknown[]) => void;
}) {
  const [text, setText] = useState(JSON.stringify(values || []));
  const [error, setError] = useState("");
  return (
    <details>
      <summary>Allowed values</summary>
      <label>
        String choices as a JSON array
        <input
          disabled={disabled}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'["urgent","normal"]'}
        />
      </label>
      <Button
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => {
          try {
            const parsed = JSON.parse(text);
            if (
              !Array.isArray(parsed) ||
              parsed.length > 32 ||
              parsed.some((x) => typeof x !== "string") ||
              new Set(parsed).size !== parsed.length
            )
              throw new Error(
                "Enter up to 32 unique strings in a JSON array. Use [] for any value.",
              );
            onChange(parsed.length ? parsed : undefined);
            setError("");
          } catch (cause) {
            setError(
              cause instanceof Error ? cause.message : "Enter a JSON array.",
            );
          }
        }}
      >
        Apply choices
      </Button>
      {error && <p role="alert">{error}</p>}
    </details>
  );
}

export function SchemaEditor({
  title,
  value,
  onChange,
  disabled,
  strict,
}: {
  title: string;
  value: string;
  onChange: (text: string) => void;
  disabled: boolean;
  strict: boolean;
}) {
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const fields = readFields(value);
  function update(next: SchemaField[]) {
    try {
      onChange(writeFields(value, next));
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not update fields.",
      );
    }
  }
  return (
    <section className="schema-card">
      <div className="row between">
        <h3>{title}</h3>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setAdvanced(!advanced)}
        >
          {advanced ? "Guided fields" : "Edit JSON"}
        </Button>
      </div>
      {error && <ErrorNotice message={error} />}
      {advanced ? (
        <label>
          {title} JSON
          <textarea
            disabled={disabled}
            className="json-editor"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            rows={17}
            spellCheck={false}
          />
        </label>
      ) : fields === null ? (
        <div>
          <p>
            This schema uses nested fields or advanced constraints. Edit its
            JSON to preserve the full contract.
          </p>
          <Button variant="outline" size="sm" onClick={() => setAdvanced(true)}>
            Open JSON editor
          </Button>
        </div>
      ) : (
        <>
          {strict && (
            <p className="field-hint">
              This provider requires every output field. Optional values can be
              represented with an empty string.
            </p>
          )}
          {strict && fields.some((f) => !f.required) && (
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              onClick={() =>
                update(fields.map((f) => ({ ...f, required: true })))
              }
            >
              Require all output fields
            </Button>
          )}
          {fields.map((field, index) => (
            <div className="schema-field" key={`${index}-${field.name}`}>
              <strong>{field.name}</strong>
              <label>
                Type of {field.name}
                <select
                  disabled={disabled}
                  value={field.type}
                  onChange={(e) =>
                    update(
                      fields.map((f, i) =>
                        i === index
                          ? {
                              ...f,
                              type: e.target.value as SchemaField["type"],
                              enum: undefined,
                            }
                          : f,
                      ),
                    )
                  }
                >
                  {["string", "number", "integer", "boolean"].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label>
                Description of {field.name}
                <input
                  disabled={disabled}
                  maxLength={500}
                  value={field.description}
                  onChange={(e) =>
                    update(
                      fields.map((f, i) =>
                        i === index ? { ...f, description: e.target.value } : f,
                      ),
                    )
                  }
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  disabled={disabled || strict}
                  checked={field.required}
                  onChange={(e) =>
                    update(
                      fields.map((f, i) =>
                        i === index ? { ...f, required: e.target.checked } : f,
                      ),
                    )
                  }
                />{" "}
                Required
              </label>
              {field.enum && (
                <p className="field-hint">
                  Allowed values: {field.enum.map(String).join(", ")}. Edit JSON
                  to change these values.
                </p>
              )}
              {field.type === "string" && (
                <StringChoices
                  key={JSON.stringify(field.enum)}
                  values={field.enum}
                  disabled={disabled}
                  onChange={(values) =>
                    update(
                      fields.map((f, i) =>
                        i === index ? { ...f, enum: values } : f,
                      ),
                    )
                  }
                />
              )}
              <Button
                size="sm"
                variant="ghost"
                disabled={disabled}
                onClick={() => update(fields.filter((_, i) => i !== index))}
              >
                Remove {field.name}
              </Button>
            </div>
          ))}
          {!fields.length && <p>No fields yet.</p>}
          <div className="row">
            <label>
              New {title.toLowerCase()} field
              <input
                disabled={disabled}
                value={newName}
                maxLength={64}
                placeholder="customer_name"
                onChange={(e) => setNewName(e.target.value)}
              />
            </label>
            <Button
              variant="outline"
              size="sm"
              disabled={disabled || !newName || fields.length >= 32}
              onClick={() => {
                const next = [
                  ...fields,
                  {
                    name: newName,
                    type: "string" as const,
                    required: true,
                    description: "",
                  },
                ];
                try {
                  const text = writeFields(value, next);
                  onChange(text);
                  setNewName("");
                  setError("");
                } catch (cause) {
                  setError(
                    cause instanceof Error
                      ? cause.message
                      : "Could not add field.",
                  );
                }
              }}
            >
              Add field
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
