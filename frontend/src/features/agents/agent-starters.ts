import type { AgentConfig } from "@/lib/api/types";

export const agentStarters: {
  id: string;
  name: string;
  description: string;
  instructions: string;
  inputSchema: AgentConfig["input_schema"];
  outputSchema: AgentConfig["output_schema"];
}[] = [
  {
    id: "triage",
    name: "Support triage",
    description: "Classify an incoming support ticket and explain its priority.",
    instructions: "Read the support ticket. Return urgent only when it describes an outage, security issue, or a customer-blocking failure. Otherwise return normal. Explain the decision briefly. Return only the fields in the output schema.",
    inputSchema: { type: "object", properties: { ticket: { type: "string" } }, required: ["ticket"], additionalProperties: false },
    outputSchema: { type: "object", properties: { priority: { type: "string", enum: ["urgent", "normal"] }, reason: { type: "string" } }, required: ["priority", "reason"], additionalProperties: false },
  },
  {
    id: "extract",
    name: "Contact extraction",
    description: "Extract a contact name, email and request from a message.",
    instructions: "Extract the sender's name, email address and request from the provided message. Use an empty string for information that is absent. Do not invent details. Return only the fields in the output schema.",
    inputSchema: { type: "object", properties: { message: { type: "string" } }, required: ["message"], additionalProperties: false },
    outputSchema: { type: "object", properties: { name: { type: "string" }, email: { type: "string" }, request: { type: "string" } }, required: ["name", "email", "request"], additionalProperties: false },
  },
  {
    id: "summarize",
    name: "Action summary",
    description: "Turn a note into a concise summary and next action.",
    instructions: "Summarize the note in one sentence and identify one concrete next action. If no action is implied, use an empty string. Do not invent facts. Return only the fields in the output schema.",
    inputSchema: { type: "object", properties: { note: { type: "string" } }, required: ["note"], additionalProperties: false },
    outputSchema: { type: "object", properties: { summary: { type: "string" }, next_action: { type: "string" } }, required: ["summary", "next_action"], additionalProperties: false },
  },
];
