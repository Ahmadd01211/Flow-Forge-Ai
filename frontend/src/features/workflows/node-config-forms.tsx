"use client";
import { useId, useState, type ReactNode } from "react";
import Link from "next/link";
import { AlertCircle, Info, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AgentConfig, Connection, GraphNode, ToolOption } from "@/lib/api/types";
import { ModelAndTools, type McpServerOption } from "@/features/agents/model-tools";
import type { SkillItem } from "@/features/agents/skills-model";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import { McpToolPicker } from "./mcp-tool-picker";
import type { components } from "@/lib/api/generated";
import {
  OPERATORS,
  isReference,
  issuesAt,
  templatePlaceholders,
  type NodeIssue,
  type Reference,
} from "./node-config";

type Config = Record<string, unknown>;
export type FormContext = {
  workflowOptions: components["schemas"]["WorkflowCallOption"][];
  refreshWorkflows: () => void;
  loadingWorkflows: boolean;
  workspaceId: string;
  workflowId: string;
  nodes: GraphNode[];
  upstream: string[];
  inputHints: string[];
  agentOptions: {
    id: string;
    name: string;
    number: number;
    provider: string;
    model_id: string;
    tool_keys: string[];
  }[];
  mcpOptions: McpServerOption[];
  toolOptions: ToolOption[];
  connections: Connection[];
  skillOptions: SkillItem[];
  httpOptions: HttpTool[];
};
type FormProps = {
  node: GraphNode;
  issues: NodeIssue[];
  onChange: (config: Config) => void;
  context: FormContext;
};

export function FieldIssues({
  issues,
  path,
  exact = false,
}: {
  issues: NodeIssue[];
  path: string;
  exact?: boolean;
}) {
  const matched = issuesAt(issues, path, exact);
  if (!matched.length) return null;
  return (
    <ul className="node-field-issues">
      {matched.map((issue) => (
        <li key={issue.message} className={issue.severity}>
          <AlertCircle size={11} />
          {issue.message}
        </li>
      ))}
    </ul>
  );
}

function without(config: Config, key: string): Config {
  return Object.fromEntries(
    Object.entries(config).filter(([name]) => name !== key),
  );
}

/** Wraps composite controls whose inputs carry their own aria-label. */
function Field({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="node-form-field">
      <span className="node-form-label">{title}</span>
      {children}
    </div>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return <p className="node-form-hint">{children}</p>;
}

function PointerInput({
  value,
  onChange,
  hints,
  placeholder = "/ticket/priority",
  label,
}: {
  value: unknown;
  onChange: (pointer: string) => void;
  hints: string[];
  placeholder?: string;
  label: string;
}) {
  const listId = useId();
  return (
    <>
      <input
        aria-label={label}
        value={typeof value === "string" ? value : ""}
        placeholder={placeholder}
        spellCheck={false}
        list={hints.length ? listId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {hints.length > 0 && (
        <datalist id={listId}>
          {hints.map((hint) => (
            <option key={hint} value={hint} />
          ))}
        </datalist>
      )}
    </>
  );
}

type LiteralType = "text" | "number" | "boolean" | "null" | "json";
function literalType(value: unknown): LiteralType {
  if (typeof value === "string") return "text";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  if (value === null) return "null";
  return "json";
}
const literalDefaults: Record<LiteralType, unknown> = {
  text: "",
  number: 0,
  boolean: true,
  null: null,
  json: {},
};

function JsonInput({
  value,
  onChange,
  label,
  rows = 4,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  label: string;
  rows?: number;
}) {
  const external = JSON.stringify(value ?? null, null, 2);
  const [text, setText] = useState(external),
    [synced, setSynced] = useState(external),
    [invalid, setInvalid] = useState(false);
  if (synced !== external) {
    // Undo or the Advanced tab replaced the value underneath this editor.
    setSynced(external);
    setText(external);
    setInvalid(false);
  }
  return (
    <>
      <textarea
        aria-label={label}
        className="json-editor"
        spellCheck={false}
        rows={rows}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          try {
            onChange(JSON.parse(event.target.value));
            setInvalid(false);
          } catch {
            setInvalid(true);
          }
        }}
      />
      {invalid && (
        <span className="field-error">
          Not valid JSON yet — the last valid value is kept.
        </span>
      )}
    </>
  );
}

function LiteralInput({
  value,
  onChange,
  label,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  label: string;
}) {
  const type = literalType(value);
  return (
    <div className="literal-input">
      <select
        aria-label={`${label} type`}
        value={type}
        onChange={(event) =>
          onChange(literalDefaults[event.target.value as LiteralType])
        }
      >
        <option value="text">Text</option>
        <option value="number">Number</option>
        <option value="boolean">True / false</option>
        <option value="null">Empty (null)</option>
        <option value="json">JSON</option>
      </select>
      {type === "text" && (
        <input
          aria-label={label}
          value={value as string}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {type === "number" && (
        <input
          aria-label={label}
          type="number"
          value={String(value)}
          onChange={(event) => {
            const parsed = Number(event.target.value);
            if (event.target.value.trim() && Number.isFinite(parsed))
              onChange(parsed);
          }}
        />
      )}
      {type === "boolean" && (
        <select
          aria-label={label}
          value={String(value)}
          onChange={(event) => onChange(event.target.value === "true")}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      )}
      {type === "json" && (
        <JsonInput label={label} value={value} onChange={onChange} rows={3} />
      )}
    </div>
  );
}

function ReferenceField({
  label,
  value,
  onChange,
  issues,
  path,
  hints,
}: {
  label: string;
  value: unknown;
  onChange: (value: Reference) => void;
  issues: NodeIssue[];
  path: string;
  hints: string[];
}) {
  const kind = isReference(value) ? value.kind : "literal";
  return (
    <fieldset className="reference-field">
      <legend>{label}</legend>
      <div
        className="segmented"
        role="radiogroup"
        aria-label={`${label} source`}
      >
        {(["input", "literal"] as const).map((option) => (
          <button
            type="button"
            role="radio"
            aria-checked={kind === option}
            key={option}
            className={kind === option ? "active" : ""}
            onClick={() =>
              kind !== option &&
              onChange(
                option === "input"
                  ? { kind: "input", pointer: "" }
                  : { kind: "literal", value: "" },
              )
            }
          >
            {option === "input" ? "Input field" : "Fixed value"}
          </button>
        ))}
      </div>
      {kind === "input" ? (
        <PointerInput
          label={`${label} field path`}
          value={(value as { pointer?: string }).pointer}
          hints={hints}
          onChange={(pointer) => onChange({ kind: "input", pointer })}
        />
      ) : (
        <LiteralInput
          label={`${label} value`}
          value={
            isReference(value) && value.kind === "literal" ? value.value : ""
          }
          onChange={(literal) => onChange({ kind: "literal", value: literal })}
        />
      )}
      <FieldIssues issues={issues} path={path} />
    </fieldset>
  );
}

function OperatorSelect({
  value,
  onChange,
  issues,
  path,
}: {
  value: unknown;
  onChange: (operator: string) => void;
  issues: NodeIssue[];
  path: string;
}) {
  return (
    <label>
      Comparison
      <select
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      >
        {!OPERATORS.some((item) => item.value === value) && (
          <option value="">Choose a comparison</option>
        )}
        {OPERATORS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
      <FieldIssues issues={issues} path={path} />
    </label>
  );
}

function ConditionForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  return (
    <>
      <ReferenceField
        label="Check"
        value={config.left}
        path="config.left"
        issues={issues}
        hints={context.inputHints}
        onChange={(left) => onChange({ ...config, left })}
      />
      <OperatorSelect
        value={config.operator}
        issues={issues}
        path="config.operator"
        onChange={(operator) =>
          onChange({
            ...config,
            operator,
            ...(operator === "exists"
              ? { right: { kind: "literal", value: null } }
              : {}),
          })
        }
      />
      {config.operator !== "exists" && (
        <ReferenceField
          label="Against"
          value={config.right}
          path="config.right"
          issues={issues}
          hints={context.inputHints}
          onChange={(right) => onChange({ ...config, right })}
        />
      )}
      <Hint>
        Both the true and false outputs must be connected and reach Return
        result. The selected path appears in the run trace.
      </Hint>
    </>
  );
}

type FieldRow = { name: string; value: unknown };
function rowsOf(fields: Record<string, unknown>): FieldRow[] {
  return Object.entries(fields).map(([name, value]) => ({ name, value }));
}

/** Named fields whose values are references; shared by transform and result steps. */
function FieldListEditor({
  title,
  fields,
  onChange,
  issues,
  newValue,
  renderValue,
}: {
  title: string;
  fields: Record<string, unknown>;
  onChange: (fields: Record<string, unknown>) => void;
  issues: NodeIssue[];
  newValue: unknown;
  renderValue: (
    value: unknown,
    path: string,
    change: (value: unknown) => void,
  ) => ReactNode;
}) {
  const external = JSON.stringify(fields);
  const [rows, setRows] = useState<FieldRow[]>(() => rowsOf(fields));
  const [synced, setSynced] = useState(external);
  const asObject = (list: FieldRow[]) =>
    Object.fromEntries(list.map((row) => [row.name, row.value]));
  if (synced !== external) {
    setSynced(external);
    if (JSON.stringify(asObject(rows)) !== external) setRows(rowsOf(fields));
  }
  const names = rows.map((row) => row.name);
  const duplicates = new Set(
    names.filter((name, index) => names.indexOf(name) !== index),
  );
  function update(next: FieldRow[]) {
    setRows(next);
    // Duplicate names would silently collapse in a JSON object, so hold them back until resolved.
    if (new Set(next.map((row) => row.name)).size === next.length)
      onChange(asObject(next));
  }
  return (
    <div className="transform-fields">
      <span className="node-form-label">{title}</span>
      {rows.map((row, index) => (
        <div className="transform-field" key={index}>
          <div className="transform-field-head">
            <input
              aria-label={`Field ${index + 1} name`}
              value={row.name}
              placeholder="field_name"
              onChange={(event) =>
                update(
                  rows.map((item, i) =>
                    i === index ? { ...item, name: event.target.value } : item,
                  ),
                )
              }
            />
            <button
              type="button"
              className="icon-button"
              aria-label={`Remove field ${row.name || index + 1}`}
              onClick={() => update(rows.filter((_, i) => i !== index))}
            >
              <Trash2 size={13} />
            </button>
          </div>
          {duplicates.has(row.name) && (
            <span className="field-error">
              Another field already uses this name.
            </span>
          )}
          {renderValue(row.value, `config.fields.${row.name}`, (value) =>
            update(
              rows.map((item, i) => (i === index ? { ...item, value } : item)),
            ),
          )}
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          let n = rows.length + 1;
          while (names.includes(`field_${n}`)) n++;
          update([...rows, { name: `field_${n}`, value: newValue }]);
        }}
      >
        <Plus size={13} />
        Add field
      </Button>
      <FieldIssues issues={issues} path="config.fields" exact />
    </div>
  );
}

function TransformForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  const fields = (
    config.fields && typeof config.fields === "object" ? config.fields : {}
  ) as Record<string, unknown>;
  const hasSchema = config.output_schema !== undefined;
  return (
    <>
      <FieldListEditor
        title="Output fields"
        fields={fields}
        issues={issues}
        newValue={{ kind: "input", pointer: "" }}
        onChange={(next) => onChange({ ...config, fields: next })}
        renderValue={(value, path, change) => (
          <ReferenceField
            label="Value"
            value={value}
            path={path}
            issues={issues}
            hints={context.inputHints}
            onChange={change}
          />
        )}
      />
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={hasSchema}
          onChange={(event) => {
            onChange(
              event.target.checked
                ? {
                    ...config,
                    output_schema: {
                      type: "object",
                      properties: Object.fromEntries(
                        Object.keys(fields).map((name) => [name, {}]),
                      ),
                    },
                  }
                : without(config, "output_schema"),
            );
          }}
        />
        Check the output against a schema
      </label>
      {hasSchema && (
        <div className="node-form-block">
          <JsonInput
            label="Output schema"
            value={config.output_schema}
            onChange={(output_schema) => onChange({ ...config, output_schema })}
            rows={6}
          />
          <FieldIssues issues={issues} path="config.output_schema" />
        </div>
      )}
    </>
  );
}

function TextTemplateForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  const template = typeof config.template === "string" ? config.template : "";
  const [field, setField] = useState("");
  const placeholders = templatePlaceholders(template);
  return (
    <>
      <label>
        Template
        <textarea
          rows={5}
          value={template}
          maxLength={4096}
          onChange={(event) =>
            onChange({ ...config, template: event.target.value })
          }
        />
        <FieldIssues issues={issues} path="config.template" />
      </label>
      <div className="insert-field">
        <PointerInput
          label="Field to insert"
          value={field}
          hints={context.inputHints}
          onChange={setField}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={!field.startsWith("/")}
          onClick={() => {
            onChange({ ...config, template: `${template}{{${field}}}` });
            setField("");
          }}
        >
          Insert
        </Button>
      </div>
      {placeholders.length > 0 && (
        <div
          className="placeholder-chips"
          aria-label="Placeholders in this template"
        >
          {placeholders.map((item, index) => (
            <code key={`${item}-${index}`}>{`{{${item}}}`}</code>
          ))}
        </div>
      )}
      <Hint>
        Placeholders are field paths in double braces, such as{" "}
        <code>{"{{/ticket/id}}"}</code>. This step outputs{" "}
        <code>{"{ text }"}</code>.
      </Hint>
    </>
  );
}

function ListFilterForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  return (
    <>
      <Field title="List to filter">
        <PointerInput
          label="List field path"
          value={config.source}
          placeholder="/items"
          hints={context.inputHints}
          onChange={(source) => onChange({ ...config, source })}
        />
        <FieldIssues issues={issues} path="config.source" />
      </Field>
      <Field title="Compare each item at">
        <PointerInput
          label="Item field path"
          value={config.item_pointer ?? ""}
          placeholder="/status (empty = the item itself)"
          hints={[]}
          onChange={(item_pointer) => onChange({ ...config, item_pointer })}
        />
        <FieldIssues issues={issues} path="config.item_pointer" />
      </Field>
      <OperatorSelect
        value={config.operator}
        issues={issues}
        path="config.operator"
        onChange={(operator) => {
          onChange(
            operator === "exists"
              ? { ...without(config, "value"), operator }
              : { ...config, operator, value: config.value ?? "" },
          );
        }}
      />
      {config.operator !== "exists" && (
        <fieldset className="reference-field">
          <legend>Value</legend>
          <LiteralInput
            label="Comparison value"
            value={config.value ?? ""}
            onChange={(value) => onChange({ ...config, value })}
          />
          <FieldIssues issues={issues} path="config.value" />
        </fieldset>
      )}
      <Hint>
        Accepts up to 200 items. This step outputs{" "}
        <code>{"{ items, count }"}</code>.
      </Hint>
    </>
  );
}

function JsonParseForm({ node, issues, onChange, context }: FormProps) {
  return (
    <>
      <Field title="Text to parse">
        <PointerInput
          label="JSON text field path"
          value={node.config.source}
          placeholder="/text"
          hints={context.inputHints}
          onChange={(source) => onChange({ ...node.config, source })}
        />
        <FieldIssues issues={issues} path="config.source" />
      </Field>
      <Hint>
        The field must hold JSON text under 64 KiB. This step outputs{" "}
        <code>{"{ value }"}</code>.
      </Hint>
    </>
  );
}

type StepOutput = { kind: "output"; node_id: string; pointer?: string };

function StepOutputPicker({
  value,
  onChange,
  sources,
}: {
  value: Partial<StepOutput>;
  onChange: (value: StepOutput) => void;
  sources: GraphNode[];
}) {
  const current = {
    kind: "output" as const,
    node_id: value.node_id ?? "",
    pointer: value.pointer ?? "",
  };
  return (
    <>
      <label>
        Step
        <select
          value={current.node_id}
          onChange={(event) =>
            onChange({ ...current, node_id: event.target.value })
          }
        >
          {!sources.some((item) => item.id === current.node_id) && (
            <option value={current.node_id}>
              {current.node_id
                ? `${current.node_id} (not upstream)`
                : "Choose a step"}
            </option>
          )}
          {sources.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <Field title="Field (optional)">
        <PointerInput
          label="Output field path"
          value={current.pointer}
          placeholder="/summary (empty = whole output)"
          hints={[]}
          onChange={(pointer) => onChange({ ...current, pointer })}
        />
      </Field>
    </>
  );
}

function ResultValueField({
  value,
  onChange,
  issues,
  path,
  sources,
  hints,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  issues: NodeIssue[];
  path: string;
  sources: GraphNode[];
  hints: string[];
}) {
  const kind = (value as { kind?: string } | null)?.kind;
  const options = [
    ["input", "Incoming data", { kind: "input", pointer: "" }],
    [
      "output",
      "Step output",
      { kind: "output", node_id: sources.at(-1)?.id ?? "", pointer: "" },
    ],
    ["literal", "Fixed value", { kind: "literal", value: "" }],
  ] as const;
  return (
    <fieldset className="reference-field">
      <legend>Value</legend>
      <div className="segmented" role="radiogroup" aria-label="Value source">
        {options.map(([option, title, initial]) => (
          <button
            type="button"
            role="radio"
            aria-checked={kind === option}
            key={option}
            className={kind === option ? "active" : ""}
            onClick={() => kind !== option && onChange(initial)}
          >
            {title}
          </button>
        ))}
      </div>
      {kind === "output" ? (
        <StepOutputPicker
          value={value as StepOutput}
          sources={sources}
          onChange={onChange}
        />
      ) : kind === "input" ? (
        <PointerInput
          label="Incoming data field path"
          value={(value as { pointer?: string }).pointer}
          hints={hints}
          onChange={(pointer) => onChange({ kind: "input", pointer })}
        />
      ) : (
        <LiteralInput
          label="Fixed value"
          value={(value as { value?: unknown } | null)?.value ?? ""}
          onChange={(literal) => onChange({ kind: "literal", value: literal })}
        />
      )}
      <FieldIssues issues={issues} path={path} />
    </fieldset>
  );
}

function ResultForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  const mode =
    config.fields !== undefined
      ? "fields"
      : config.value !== undefined
        ? "value"
        : "incoming";
  const sources = context.nodes.filter((item) =>
    context.upstream.includes(item.id),
  );
  const last = sources.at(-1)?.id ?? "";
  const modes = [
    ["incoming", "Incoming data", {}],
    [
      "value",
      "One step",
      { value: { kind: "output", node_id: last, pointer: "" } },
    ],
    [
      "fields",
      "Build fields",
      { fields: { result: { kind: "output", node_id: last, pointer: "" } } },
    ],
  ] as const;
  return (
    <>
      <fieldset className="reference-field">
        <legend>Return</legend>
        <div className="segmented" role="radiogroup" aria-label="Result shape">
          {modes.map(([option, title, initial]) => (
            <button
              type="button"
              role="radio"
              aria-checked={mode === option}
              key={option}
              className={mode === option ? "active" : ""}
              onClick={() => mode !== option && onChange(initial)}
            >
              {title}
            </button>
          ))}
        </div>
        {mode === "value" && (
          <StepOutputPicker
            value={config.value as StepOutput}
            sources={sources}
            onChange={(value) => onChange({ value })}
          />
        )}
        <FieldIssues issues={issues} path="config.value" />
      </fieldset>
      {mode === "fields" && (
        <FieldListEditor
          title="Result fields"
          fields={config.fields as Record<string, unknown>}
          issues={issues}
          newValue={{ kind: "input", pointer: "" }}
          onChange={(fields) => onChange({ fields })}
          renderValue={(value, path, change) => (
            <ResultValueField
              value={value}
              path={path}
              issues={issues}
              sources={sources}
              hints={context.inputHints}
              onChange={change}
            />
          )}
        />
      )}
      <Hint>
        {mode === "incoming"
          ? "Returns whatever arrives from the connected path. Use this when branches rejoin here."
          : mode === "value"
            ? "Returns one earlier step's output. With a condition, pick a step that runs on every path."
            : "Builds the workflow output from earlier steps, the incoming data and fixed values. Steps skipped by a condition cannot be read; use incoming data to merge branches."}
      </Hint>
    </>
  );
}

const REPLY_SCHEMA = {
  type: "object",
  properties: { reply: { type: "string" } },
  required: ["reply"],
  additionalProperties: false,
};

function LlmForm({ node, issues, onChange, context }: FormProps) {
  const config = node.config;
  const limits = (config.limits as Record<string, unknown> | undefined) ?? {};
  const structured = config.output_schema !== undefined;
  const memory = config.memory as { key_pointer: string; max_turns: number; retention_days: number } | null | undefined;
  const skills = (config.skills as { skill_id: string; name: string; description: string }[] | undefined) ?? [];
  const workflowTools = (config.workflow_tools as { version_id: string; name: string; description: string }[] | undefined) ?? [];
  // Tool workflows cannot call models or pause, and a workflow cannot offer itself.
  const toolWorkflows = context.workflowOptions.filter((option) => !option.agent_steps && !option.has_pause);
  const setLimit = (key: string, value: unknown) => onChange({ ...config, limits: { ...limits, [key]: value } });
  return (
    <>
      <label>
        Instructions
        <textarea
          rows={6}
          maxLength={32000}
          value={typeof config.instructions === "string" ? config.instructions : ""}
          placeholder="You answer customer questions using the order data you receive. Look up shipping status with the tool when asked."
          onChange={(event) => onChange({ ...config, instructions: event.target.value })}
        />
        <FieldIssues issues={issues} path="config.instructions" />
      </label>
      <Hint>The model receives the data arriving at this step as JSON. Instructions guide behaviour; tool grants decide what it can reach.</Hint>
      <div className="llm-model-tools">
        <ModelAndTools
          workspaceId={context.workspaceId}
          config={{
            provider: (config.provider as AgentConfig["provider"]) ?? "openai",
            model_id: typeof config.model_id === "string" ? config.model_id : "",
            tool_keys: (config.tool_keys as AgentConfig["tool_keys"]) ?? [],
            mcp_tools: (config.mcp_tools as AgentConfig["mcp_tools"]) ?? [],
            http_tools: (config.http_tools as AgentConfig["http_tools"]) ?? [],
          }}
          setConfig={(next) => onChange({ ...config, ...next })}
          connections={context.connections}
          tools={context.toolOptions}
          mcpServers={context.mcpOptions}
          httpTools={context.httpOptions}
        />
        <FieldIssues issues={issues} path="config.model_id" />
      </div>
      <fieldset className="reference-field">
        <legend>Output</legend>
        <div className="segmented" role="radiogroup" aria-label="Output shape">
          <button type="button" role="radio" aria-checked={!structured} className={!structured ? "active" : ""} onClick={() => structured && onChange(without(config, "output_schema"))}>
            Text reply
          </button>
          <button type="button" role="radio" aria-checked={structured} className={structured ? "active" : ""} onClick={() => !structured && onChange({ ...config, output_schema: REPLY_SCHEMA })}>
            Structured JSON
          </button>
        </div>
        {structured ? (
          <JsonInput label="Output schema" value={config.output_schema} onChange={(output_schema) => onChange({ ...config, output_schema })} rows={8} />
        ) : (
          <Hint>Returns <code>{"{ reply }"}</code> with the model&apos;s answer as text.</Hint>
        )}
        <FieldIssues issues={issues} path="config.output_schema" />
      </fieldset>
      <fieldset className="reference-field">
        <legend>Skills</legend>
        {context.skillOptions.length ? context.skillOptions.map((skill) => {
          const attached = skills.some((grant) => grant.skill_id === skill.id);
          return (
            <label className="checkbox-row" key={skill.id}>
              <input type="checkbox" checked={attached} disabled={!attached && skills.length >= 8} onChange={(event) => onChange({ ...config, skills: event.target.checked ? [...skills, { skill_id: skill.id, name: skill.name, description: skill.description }] : skills.filter((grant) => grant.skill_id !== skill.id) })} />
              {skill.name}{skill.latest ? ` · v${skill.latest.number}` : " · draft, publish it first"}
            </label>
          );
        }) : <Hint>No skills yet. Add starters in Agents → Skills.</Hint>}
        <Hint>Publishing the workflow pins each skill's latest version.</Hint>
        <FieldIssues issues={issues} path="config.skills" />
      </fieldset>
      <fieldset className="reference-field">
        <legend>Memory</legend>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={!!memory}
            onChange={(event) => onChange(event.target.checked ? { ...config, memory: { key_pointer: "/conversation_id", max_turns: 10, retention_days: 30 } } : without(config, "memory"))}
          />
          Remember earlier messages in a conversation
        </label>
        {memory && (
          <>
            <Field title="Conversation ID field">
              <PointerInput label="Conversation ID field path" value={memory.key_pointer} placeholder="/conversation_id" hints={context.inputHints} onChange={(key_pointer) => onChange({ ...config, memory: { ...memory, key_pointer } })} />
            </Field>
            <label>
              Exchanges to remember
              <input type="number" min={1} max={20} value={memory.max_turns} onChange={(event) => onChange({ ...config, memory: { ...memory, max_turns: Number(event.target.value) } })} />
            </label>
            <label>
              Keep for (days)
              <input type="number" min={1} max={90} value={memory.retention_days} onChange={(event) => onChange({ ...config, memory: { ...memory, retention_days: Number(event.target.value) } })} />
            </label>
            <Hint>Earlier turns are sent to the model as <code>history</code> alongside the new <code>input</code>. They are encrypted at rest and deleted after the retention period.</Hint>
          </>
        )}
        <FieldIssues issues={issues} path="config.memory" />
      </fieldset>
      <fieldset className="reference-field">
        <legend>Workflows it can run</legend>
        {toolWorkflows.length ? (
          toolWorkflows.map((option) => {
            const selected = workflowTools.some((grant) => grant.version_id === option.id);
            return (
              <label className="checkbox-row" key={option.id}>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={!selected && workflowTools.length >= 4}
                  onChange={(event) =>
                    onChange({
                      ...config,
                      workflow_tools: event.target.checked
                        ? [...workflowTools, { version_id: option.id, name: option.name, description: "" }]
                        : workflowTools.filter((grant) => grant.version_id !== option.id),
                    })
                  }
                />
                {option.name} · v{option.number}{option.has_external ? " · calls external services" : ""}
              </label>
            );
          })
        ) : (
          <Hint>Publish a workflow without agent, LLM, approval or timer steps to offer it here.</Hint>
        )}
        <Hint>The model can start up to three of these per run. They run inside this workflow run and share its budget and deadline.</Hint>
        <FieldIssues issues={issues} path="config.workflow_tools" />
      </fieldset>
      <fieldset className="reference-field">
        <legend>Limits</legend>
        <label>
          Budget per run (USD)
          <input value={String(limits.max_cost_usd ?? "0.10")} inputMode="decimal" onChange={(event) => setLimit("max_cost_usd", event.target.value)} />
        </label>
        <label>
          Tool calls per run
          <input type="number" min={0} max={32} value={Number(limits.max_tool_calls ?? 8)} onChange={(event) => setLimit("max_tool_calls", Number(event.target.value))} />
        </label>
        <FieldIssues issues={issues} path="config.limits" />
      </fieldset>
      <Hint>Publishing freezes these settings with the workflow version. Each run re-checks the provider key, tool approvals and both this budget and the workflow budget.</Hint>
    </>
  );
}

function AgentForm({ node, issues, onChange, context }: FormProps) {
  return (
    <>
      <label>
        Published agent version
        <select
          value={String(node.config.version_id || "")}
          onChange={(event) =>
            onChange({ ...node.config, version_id: event.target.value })
          }
        >
          <option value="">Choose an agent version</option>
          {context.agentOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name} · v{option.number} · {option.provider}/
              {option.model_id}
              {option.tool_keys.length
                ? ` · ${option.tool_keys.length} tools`
                : ""}
            </option>
          ))}
        </select>
        <FieldIssues issues={issues} path="config.version_id" />
      </label>
      <Hint>
        Select an immutable published agent. Its provider key, input schema,
        tool approvals and budget are checked again at run time. Tool calls
        currently work with OpenAI GPT-5 Mini.
      </Hint>
      <Link href={`/w/${context.workspaceId}/agents/new`} className="text-link">
        {context.agentOptions.length
          ? "Create another agent"
          : "Create and publish an agent first"}
      </Link>
    </>
  );
}

function ToolForm({ node, issues, onChange, context }: FormProps) {
  const selected = context.toolOptions.find(
    (tool) => tool.key === node.config.tool_key,
  );
  const properties = Object.keys(selected?.input_schema.properties ?? {});
  return (
    <>
      <label>
        Reviewed tool
        <select
          value={String(node.config.tool_key ?? "")}
          onChange={(event) =>
            onChange({ ...node.config, tool_key: event.target.value })
          }
        >
          {!selected && <option value="">Choose a tool</option>}
          {context.toolOptions.map((tool) => (
            <option key={tool.key} value={tool.key}>
              {tool.name}
              {tool.installed ? "" : " (needs approval)"}
            </option>
          ))}
        </select>
        <FieldIssues issues={issues} path="config.tool_key" />
      </label>
      {selected && (
        <div className="tool-contract">
          <p>{selected.description}</p>
          <span className="node-form-label">Expects input</span>
          <div className="placeholder-chips">
            {properties.map((name) => (
              <code key={name}>
                {name}
                {selected.input_schema.required?.includes(name) ? "" : "?"}
              </code>
            ))}
          </div>
        </div>
      )}
      <Hint>
        The tool receives this step&apos;s input as-is. Shape it with a
        Transform step first if the fields differ.
      </Hint>
      {selected && !selected.installed && (
        <Link href={`/w/${context.workspaceId}/tools`} className="text-link">
          Approve it in the Tool Registry
        </Link>
      )}
    </>
  );
}

function McpToolForm({ node, issues, onChange, context }: FormProps) {
  const serverId = String(node.config.server_id || ""),
    toolName = String(node.config.tool_name || "");
  const schema = context.mcpOptions.find((server) => server.id === serverId)
    ?.runnable_schemas[toolName];
  return (
    <>
      <McpToolPicker
        workspaceId={context.workspaceId}
        servers={context.mcpOptions}
        value={{ server_id: serverId, tool_name: toolName }}
        onChange={onChange}
      />
      <FieldIssues issues={issues} path="config.server_id" />
      <FieldIssues issues={issues} path="config.tool_name" />
      <Hint>
        The workflow pins this connection generation and tool schema when
        published. Changes require a new workflow version.
      </Hint>
      {schema !== undefined && (
        <pre className="tool-output">{JSON.stringify(schema, null, 2)}</pre>
      )}
    </>
  );
}

function MergeForm({ node, onChange, issues }: FormProps) {
  return (
    <>
      <label>
        Paths to merge
        <select
          value={String(node.config.mode || "active")}
          onChange={(e) => onChange({ ...node.config, mode: e.target.value })}
        >
          <option value="active">Active paths</option>
          <option value="all">Every connected path</option>
        </select>
        <FieldIssues issues={issues} path="config.mode" />
      </label>
      <Hint>
        Waits until all incoming paths are resolved. Active paths merge
        whichever branches ran; every path skips this step if any incoming path
        was skipped. One active input passes through; multiple inputs are
        grouped by source step ID.
      </Hint>
    </>
  );
}

function TriggerInfo({ node, context }: FormProps) {
  return (
    <div className="permission-callout">
      <Info size={17} />
      {node.type === "manual_input" ? (
        <p>
          Input arrives as a JSON object and is checked against the workflow
          input schema before any step runs. Later steps read it with field
          paths such as <code>/ticket/id</code>.
        </p>
      ) : node.type === "chat_trigger" ? (
        <p>
          Each chat message starts a run with <code>{"{ conversation_id, message }"}</code>.
          Give an LLM step memory on <code>/conversation_id</code> to continue the conversation.
          Publish, then open the{" "}
          <Link href={`/w/${context.workspaceId}/workflows/${context.workflowId}/chat`} className="text-link">
            chat
          </Link>
          , or send the same input from your app through a deployment.
        </p>
      ) : (
        <p>
          Publish this workflow, then open{" "}
          <Link
            href={`/w/${context.workspaceId}/automations`}
            className="text-link"
          >
            Triggers &amp; schedules
          </Link>
          {node.type === "schedule_trigger"
            ? " to set its interval and encrypted input."
            : " to create an authenticated webhook endpoint."}{" "}
          Connection keys and scheduling settings stay outside the published
          graph.
        </p>
      )}
    </div>
  );
}

function HttpToolForm({ node, issues, onChange, context }: FormProps) {
  const tools = context.httpOptions.filter((tool) => tool.state === "active");
  const selected = tools.find((tool) => tool.id === node.config.tool_id);
  return (
    <>
      <label>
        Approved API tool
        <select
          value={String(node.config.tool_id || "")}
          onChange={(event) => onChange({ tool_id: event.target.value })}
        >
          {!selected && (
            <option value={String(node.config.tool_id || "")}>
              Choose an approved endpoint
            </option>
          )}
          {tools.map((tool) => (
            <option key={tool.id} value={tool.id}>
              {tool.name} · {tool.method}
            </option>
          ))}
        </select>
      </label>
      <FieldIssues issues={issues} path="config.tool_id" />
      {selected && (
        <>
          <code className="http-url">
            {selected.method} {selected.url}
          </code>
          <Hint>{selected.description}</Hint>
          <Hint>
            {selected.read_only
              ? "Read-only service call."
              : "This step can change data in the connected service. Execute a published run to retain receipts. Automatic retries are disabled."}{" "}
            Map incoming data to the contract below. Service charges are
            separate from model budgets.
          </Hint>
          <details>
            <summary>Input contract</summary>
            <pre className="json-editor">
              {JSON.stringify(selected.input_schema, null, 2)}
            </pre>
          </details>
          <details>
            <summary>Output contract</summary>
            <pre className="json-editor">
              {JSON.stringify(selected.output_schema, null, 2)}
            </pre>
          </details>
        </>
      )}
      <Link className="text-link" href={`/w/${context.workspaceId}/tools`}>
        Manage API tools
      </Link>
    </>
  );
}

function WorkflowCallForm({ node, issues, onChange, context }: FormProps) {
  const selected = context.workflowOptions.find(
    (option) => option.id === node.config.version_id,
  );
  const loop = node.type === "for_each";
  return (
    <>
      <label>
        Published workflow version
        <select
          value={String(node.config.version_id || "")}
          onChange={(event) =>
            onChange({
              ...without(node.config, "graph_hash"),
              version_id: event.target.value,
            })
          }
        >
          {!selected && (
            <option value={String(node.config.version_id || "")}>
              {node.config.version_id
                ? "Version unavailable — choose another"
                : "Choose a published workflow"}
            </option>
          )}
          {context.workflowOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name} · v{option.number}
              {option.has_external ? " · external services" : " · local"}
            </option>
          ))}
        </select>
      </label>
      <FieldIssues issues={issues} path="config.version_id" />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={context.loadingWorkflows}
        onClick={context.refreshWorkflows}
      >
        {context.loadingWorkflows
          ? "Refreshing…"
          : "Refresh published versions"}
      </Button>
      <Hint>
        Calls the exact published version. Publishing a newer child does not
        change this workflow. The parent shares its run budget and deadline with
        every child.
      </Hint>
      {loop && (
        <>
          <Field title="List field">
            <PointerInput
              label="Loop list field"
              value={node.config.source}
              hints={context.inputHints}
              placeholder="/items"
              onChange={(source) => onChange({ ...node.config, source })}
            />
          </Field>
          <FieldIssues issues={issues} path="config.source" />
          <label>
            Child input
            <select
              value={String(node.config.input_mode || "envelope")}
              onChange={(event) =>
                onChange({ ...node.config, input_mode: event.target.value })
              }
            >
              <option value="envelope">
                Item and index — {"{item, index}"}
              </option>
              <option value="item">Item object itself</option>
            </select>
          </label>
          <FieldIssues issues={issues} path="config.input_mode" />
          <label>
            Maximum items
            <input
              type="number"
              min={1}
              max={20}
              value={Number(node.config.max_items ?? 3)}
              onChange={(event) =>
                onChange({
                  ...node.config,
                  max_items: Number(event.target.value),
                })
              }
            />
          </label>
          <FieldIssues issues={issues} path="config.max_items" />
          <Hint>
            Items run one at a time in their original order. All inputs are
            checked before the first child starts. Oversized lists fail; items
            are never silently dropped. The output is {"{items: [...], count}"}.
            On failure, inspect completed items before replaying.
          </Hint>
        </>
      )}
      {selected && (
        <>
          <div className="node-info-card">
            <strong>
              {selected.name} · v{selected.number}
            </strong>
            <p>
              {selected.expanded_steps} steps and {selected.agent_steps} agent
              calls per invocation.{" "}
              {loop
                ? `Up to ${Number(node.config.max_items || 0) * selected.expanded_steps} child steps at this item limit.`
                : "The child output becomes this step's output."}
            </p>
            <p>
              Child cap ${String(selected.limits.max_cost_usd)} per invocation;
              timeout {String(selected.limits.timeout_seconds)}s, bounded by the
              parent's remaining allowance.
            </p>
            {selected.has_external && (
              <p>
                This version calls external services. Use a published run to
                retain receipts and usage.
              </p>
            )}
            {selected.has_pause && (
              <p>
                This version contains approvals or timers. Use a published run;
                the worker releases while waiting.
              </p>
            )}
          </div>
          <details>
            <summary>Child input contract</summary>
            <pre className="json-editor">
              {JSON.stringify(selected.input_schema, null, 2)}
            </pre>
          </details>
          <details>
            <summary>Child output contract</summary>
            <pre className="json-editor">
              {JSON.stringify(selected.output_schema, null, 2)}
            </pre>
          </details>
          <Link
            className="text-link"
            href={`/w/${context.workspaceId}/workflows/${selected.workflow_id}/edit`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open child workflow in a new tab
          </Link>
        </>
      )}
      {!context.workflowOptions.length && (
        <Hint>
          Publish another workflow first. Current-workflow versions and
          dependencies that are no longer executable are excluded.
        </Hint>
      )}
    </>
  );
}

function PauseForm({ node, issues, onChange }: FormProps) {
  const approval = node.type === "approval";
  return (
    <>
      <Hint>
        {approval
          ? "An owner or admin reviews the saved step input from Workflow executions. Approval passes that exact input onward; rejection or expiry ends the run."
          : "A durable timer releases the worker and resumes automatically, including after a restart. Incoming data passes through unchanged."}{" "}
        Parked runs retain their workspace run slot and model budget
        reservation. Active execution time excludes the parked duration.
      </Hint>
      {approval && (
        <>
          <label>
            Review instructions
            <textarea
              aria-label="Review instructions"
              maxLength={500}
              rows={4}
              value={String(node.config.prompt ?? "")}
              onChange={(e) =>
                onChange({ ...node.config, prompt: e.target.value })
              }
            />
          </label>
          <FieldIssues issues={issues} path="config.prompt" />
          <label>
            <input
              type="checkbox"
              checked={node.config.allow_requester === true}
              onChange={(e) =>
                onChange({ ...node.config, allow_requester: e.target.checked })
              }
            />{" "}
            Allow the run requester to approve, if they are an owner or admin
          </label>
          <Hint>
            Leave this off when a second person must review the request. For a
            single-person local test, enable it explicitly.
          </Hint>
        </>
      )}
      <label>
        {approval
          ? "Decision expires after (seconds)"
          : "Wait duration (seconds)"}
        <input
          aria-label={
            approval ? "Decision expiry in seconds" : "Wait duration in seconds"
          }
          type="number"
          min={approval ? 60 : 1}
          max={86400}
          value={Number(
            node.config[approval ? "expires_seconds" : "seconds"] ??
              (approval ? 3600 : 60),
          )}
          onChange={(e) =>
            onChange({
              ...node.config,
              [approval ? "expires_seconds" : "seconds"]: Number(
                e.target.value,
              ),
            })
          }
        />
      </label>
      <FieldIssues
        issues={issues}
        path={approval ? "config.expires_seconds" : "config.seconds"}
      />
      <Hint>
        The sum of all timer durations and approval expiries must fit within 24
        hours, including every allowed loop item.
      </Hint>
    </>
  );
}

const forms: Record<GraphNode["type"], (props: FormProps) => ReactNode> = {
  approval: PauseForm,
  wait: PauseForm,
  manual_input: TriggerInfo,
  webhook_trigger: TriggerInfo,
  schedule_trigger: TriggerInfo,
  chat_trigger: TriggerInfo,
  agent: AgentForm,
  llm: LlmForm,
  tool: ToolForm,
  mcp_tool: McpToolForm,
  http_tool: HttpToolForm,
  subworkflow: WorkflowCallForm,
  for_each: WorkflowCallForm,
  condition: ConditionForm,
  merge: MergeForm,
  transform: TransformForm,
  text_template: TextTemplateForm,
  list_filter: ListFilterForm,
  json_parse: JsonParseForm,
  result: ResultForm,
};

export function NodeConfigForm(props: FormProps) {
  const Form = forms[props.node.type];
  // Fields render their own issues; this catches node-wide ones and keys no field owns.
  const general = props.issues.filter(
    (issue) =>
      !issue.path ||
      issue.path === "config" ||
      issue.path.startsWith("policy.") ||
      issue.code === "NODE_CONFIG_UNUSED",
  );
  return (
    <div className="node-form">
      {general.length > 0 && (
        <ul className="node-field-issues node-general-issues">
          {general.map((issue, index) => (
            <li key={index} className={issue.severity}>
              <AlertCircle size={11} />
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      <Form {...props} />
    </div>
  );
}
