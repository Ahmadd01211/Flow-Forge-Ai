/** Reviewed setup recipes. These fill the existing fixed-destination permission form. */
export type ConnectorRecipe = "github-read" | "github-issue" | "slack-message";
type Schema = Record<string, unknown>;

function object(
  properties: Record<string, unknown>,
  required: string[] = [],
): Schema {
  return { type: "object", properties, required, additionalProperties: false };
}

export function connectorPreset(
  recipe: ConnectorRecipe,
  owner: string,
  repository: string,
  channel: string,
) {
  if (recipe === "slack-message") {
    if (!/^[CG][A-Z0-9]{8,31}$/.test(channel))
      throw new Error(
        "Enter a Slack channel ID such as C0123456789. Invite your bot to that channel first.",
      );
    return {
      name: "Slack · Send channel message",
      description: `Post a message to the approved Slack channel ${channel}.`,
      url: "https://slack.com/api/chat.postMessage",
      method: "POST" as const,
      readOnly: false,
      inputSchema: object(
        {
          channel: { const: channel },
          text: { type: "string", minLength: 1, maxLength: 4000 },
          unfurl_links: { const: false },
          unfurl_media: { const: false },
          mrkdwn: { const: false },
        },
        ["channel", "text", "unfurl_links", "unfurl_media", "mrkdwn"],
      ),
      outputSchema: {
        type: "object",
        properties: {
          status_code: { const: 200 },
          body: {
            type: "object",
            properties: {
              ok: { const: true },
              channel: { const: channel },
              ts: { type: "string" },
            },
            required: ["ok", "channel", "ts"],
          },
        },
        required: ["status_code", "body"],
      },
      sample: {
        channel,
        text: "A customer record has been approved.",
        unfurl_links: false,
        unfurl_media: false,
        mrkdwn: false,
      },
      instructions:
        "Use an installed Slack app bot token with chat:write. Invite the bot to this channel. This contract binds the channel and disables formatting and link previews. Sending requires a published workflow; it cannot be tested as a disposable write.",
      docs: "https://docs.slack.dev/reference/methods/chat.postMessage/",
    };
  }
  if (
    !/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/.test(owner) ||
    !/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$/.test(repository) ||
    repository === "." ||
    repository === ".."
  )
    throw new Error(
      "Enter a GitHub account and repository name, without URLs, slashes or query fields.",
    );
  const write = recipe === "github-issue";
  return {
    name: `GitHub · ${write ? "Create issue" : "List issues"}`,
    description: `${write ? "Create an issue" : "Read issues and pull requests"} in ${owner}/${repository}.`,
    url: `https://api.github.com/repos/${owner}/${repository}/issues`,
    method: write ? ("POST" as const) : ("GET" as const),
    readOnly: !write,
    inputSchema: write
      ? object(
          {
            title: { type: "string", minLength: 1, maxLength: 200 },
            body: { type: "string", maxLength: 4000 },
          },
          ["title"],
        )
      : object(
          {
            state: { enum: ["open", "closed", "all"] },
            per_page: { type: "integer", minimum: 1, maximum: 10 },
            page: { type: "integer", minimum: 1, maximum: 100 },
          },
          ["per_page"],
        ),
    outputSchema: {
      type: "object",
      properties: {
        status_code: { const: write ? 201 : 200 },
        body: write
          ? {
              type: "object",
              properties: {
                number: { type: "integer" },
                html_url: { type: "string" },
              },
              required: ["number", "html_url"],
            }
          : { type: "array" },
      },
      required: ["status_code", "body"],
    },
    sample: write
      ? {
          title: "Customer follow-up",
          body: "Review the approved customer record.",
        }
      : { state: "open", per_page: 5, page: 1 },
    instructions: `Use a fine-grained token limited to this repository with Issues ${write ? "write" : "read"} permission. ${write ? "Creating an issue requires a published workflow and may trigger repository notifications." : "The Issues API also returns pull requests. Large issue bodies can exceed the 64 KiB response limit; reduce per_page when needed."} Credentials are verified only when you make a request.`,
    docs: "https://docs.github.com/en/rest/issues/issues",
  };
}
