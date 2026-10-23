import { z } from "zod";
const credentialsSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password.").max(128),
});

export function authSchema(mode: "login" | "register") {
  return credentialsSchema
    .extend({
      name: z.string().trim().max(100).optional(),
      workspace_name: z.string().trim().max(100).optional(),
    })
    .superRefine((value, ctx) => {
      if (mode === "register") {
        if (!value.name)
          ctx.addIssue({
            code: "custom",
            path: ["name"],
            message: "Enter your name.",
          });
        if (!value.workspace_name)
          ctx.addIssue({
            code: "custom",
            path: ["workspace_name"],
            message: "Name your workspace.",
          });
        if (value.password.length < 12)
          ctx.addIssue({
            code: "custom",
            path: ["password"],
            message: "Use at least 12 characters.",
          });
      }
    });
}
