# Guided GitHub and Slack tools

Open **Tool Registry → API tools → Add API tool**. Choose a service recipe, enter its repository or channel, then select **Fill permission form**. The recipe fills the existing destination, method and contracts. Review them, enter a token in the password field and approve the tool. Filling the form makes no request to the service and never verifies a token implicitly.

The local release includes three recipes:

| Recipe | Fixed target | Required credential permission | Execution |
|---|---|---|---|
| GitHub: List repository issues | One `api.github.com/repos/{owner}/{repo}/issues` endpoint | Fine-grained token restricted to that repository, Issues read | Confirmed read test or approved agent/workflow |
| GitHub: Create repository issue | Same repository endpoint, POST | Fine-grained token restricted to that repository, Issues write | Published workflow only |
| Slack: Send channel message | `slack.com/api/chat.postMessage`, with one channel ID bound in the input contract | Installed app bot token with `chat:write`, bot invited to that channel | Published workflow only |

See the official [GitHub Issues API](https://docs.github.com/en/rest/issues/issues) and [Slack chat.postMessage API](https://docs.slack.dev/reference/methods/chat.postMessage/) for account setup and permissions. GitHub's Issues API also returns pull requests. Use small pages: the recipe requires `per_page` between one and ten, and the existing response ceiling remains 64 KiB. A repository with very large issue bodies can still exceed it. Slack's response can report a failure with HTTP 200; the transport now recognizes that as a failed action, with bounded diagnostics for revoked tokens, missing scope and channel membership. Unrecognized service text is not echoed into an error message.

After approval, select the API tool in a workflow's **HTTP API tool** node. Shape the input using Transform or field mappings. For Slack, the recipe's sample includes `channel`, `text`, `unfurl_links:false`, `unfurl_media:false` and `mrkdwn:false`; the input schema requires these fixed safety options and the selected channel. The success contract checks `ok:true` and the same channel. The recipe does not grant access to all channels.

Write actions cannot be tested with the disposable read-test button. Publish and run a workflow to retain checkpoints and receipts. Put a **Human approval** node before a write when a person must review its input. Inspect the target service before replaying a failed write whose outcome is uncertain. Retrying the same decision or polling a run does not resend a completed action.

These are guided credential-based recipes using the established HTTP permission boundary, not OAuth installations. Each approved endpoint has its own encrypted credential and immutable generation/spec hash. Rotation or revocation invalidates old grants; republish consumers as required. Existing SSRF restrictions, IP-pinned HTTPS/TLS identity, redirect/proxy blocking and bounded JSON transport remain active. No credential is copied into portable templates or activity exports.

## Why reuse HTTP tools

One reviewed permission/transport path is easier to maintain than separate network clients with subtly different security and recovery behavior. Recipes make common setup simpler while preserving a custom API option. They do not automatically widen permissions or discover private repositories/channels. OAuth, refresh-token rotation, installation revocation and vendor-specific pagination/rate-limit automation need a complete lifecycle and real test accounts before they can be represented as working integrations.

Recipe tests validate fixed destinations, path/parameter injection rejection, bound Slack channel/options and success contracts. Transport tests use controlled Slack HTTP responses. No real GitHub issue or Slack message was created during verification; account-specific acceptance remains to be done through the local interface with a user-controlled test repository/channel.
