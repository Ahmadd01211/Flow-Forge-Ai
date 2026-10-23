import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";
mkdirSync(".local", { recursive: true });
const temporary = resolve(".local", `api-${process.pid}.ts`);
try {
  const result = spawnSync(
    process.execPath,
    [
      "node_modules/openapi-typescript/bin/cli.js",
      "../backend/openapi.json",
      "-o",
      temporary,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) throw new Error("API type generation failed.");
  if (
    readFileSync(temporary, "utf8").replaceAll("\r\n", "\n") !==
    readFileSync("src/lib/api/generated.ts", "utf8").replaceAll("\r\n", "\n")
  )
    throw new Error("API types are stale. Run npm run api:generate.");
  console.log("Frontend API types match OpenAPI.");
} finally {
  try {
    unlinkSync(temporary);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}
