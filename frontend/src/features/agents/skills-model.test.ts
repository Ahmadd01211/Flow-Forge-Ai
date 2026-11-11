import { describe, expect, it } from "vitest";
import { toolLabel } from "./builder-model";
import { groupStarters, newerSkillVersion, type SkillItem, type StarterSkill } from "./skills-model";

const skill = (number: number | null) => ({ id: "s1", latest: number ? { version_id: "v", number } : null }) as SkillItem;

describe("skills helpers", () => {
  it("groups starters in catalog order", () => {
    const starters = [
      { key: "a", group: "Writing & tone" }, { key: "b", group: "Support" }, { key: "c", group: "Writing & tone" },
    ] as StarterSkill[];
    expect(groupStarters(starters).map(([group, items]) => [group, items.map((item) => item.key)])).toEqual([
      ["Writing & tone", ["a", "c"]], ["Support", ["b"]],
    ]);
  });

  it("spots a newer skill version than the one the live agent pins", () => {
    expect(newerSkillVersion([{ skill_id: "s1", number: 1 }], skill(2))).toBe(2);
    expect(newerSkillVersion([{ skill_id: "s1", number: 2 }], skill(2))).toBeNull();
    expect(newerSkillVersion(undefined, skill(2))).toBeNull();
    expect(newerSkillVersion([{ skill_id: "other", number: 1 }], skill(3))).toBeNull();
  });

  it("labels skill loads in the live chat", () => {
    expect(toolLabel("skill:Brand voice")).toBe("skill · Brand voice");
  });
});
