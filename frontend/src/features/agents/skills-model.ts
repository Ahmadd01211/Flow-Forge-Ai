/** Shapes from GET /workspaces/{id}/skills and helpers shared by the skill screens and the builder. */

export interface SkillExample { input: string; output: string }
export interface SkillConfig {
  instructions: string;
  examples: SkillExample[];
  tool_keys: string[];
  mcp_tools: { server_id: string; tool_name: string; description: string; input_schema?: Record<string, unknown> }[];
  http_tools: { tool_id: string; name: string; description: string; input_schema?: Record<string, unknown> }[];
}
export interface SkillItem {
  id: string;
  name: string;
  description: string;
  config: SkillConfig;
  revision: number;
  starter_key: string | null;
  updated_at: string;
  status: "draft" | "published" | "changed";
  latest: { version_id: string; number: number } | null;
  used_by: string[];
  tool_count?: number;
}
export interface StarterSkill { key: string; group: string; emoji: string; name: string; description: string; added: boolean }

export function groupStarters(starters: StarterSkill[]): [string, StarterSkill[]][] {
  const groups = new Map<string, StarterSkill[]>();
  for (const starter of starters) groups.set(starter.group, [...(groups.get(starter.group) ?? []), starter]);
  return [...groups.entries()];
}

/** Whether the agent's live version pins an older skill version than the newest published one. */
export function newerSkillVersion(pinned: { skill_id: string; number?: number | null }[] | undefined, skill: SkillItem): number | null {
  const grant = pinned?.find((item) => item.skill_id === skill.id);
  return grant?.number && skill.latest && skill.latest.number > grant.number ? skill.latest.number : null;
}
