# WORLDSEED memory and coding context

Repository files are the durable memory. Obsidian supplies navigation; Smart
Connections adds related-note retrieval; Context7 supplies external library docs.
None of these tools changes game state or creates NPC memory.

## Obsidian and Smart Connections

1. In Obsidian, choose **Open folder as vault** and select this checkout's `docs`
   folder. Shared settings use standard relative Markdown links. New notes default
   to `development/memory`; renaming does not automatically rewrite project links.
2. Open [START_HERE](memory/START_HERE.md). Existing guides and handoffs remain in
   their original paths. Read the root `AGENTS.md` in your code editor before edits.
3. On your desktop, install **Smart Connections** through Obsidian's Community
   Plugins settings and enable it. This repository does not install or enable
   community code. Retain the default local embedding workflow initially and
   inspect the plugin's indexed-source settings before indexing.
4. Let indexing finish. Open a known document, inspect related passages, and verify
   the original source and applicability before reusing a result. Templates and
   superseded handoffs are not accepted decisions just because they match a query.

Smart Connections Core uses local embeddings by default and requires no API key
for related-note retrieval. Cloud providers are optional and can receive selected
text when configured. Vault chat is a separate capability, not provided by this
configuration. See [Smart Connections](https://smartconnections.app/smart-connections/)
and [Obsidian's local storage model](https://obsidian.md/help/data-storage).
Plugin binaries, indexes, device layouts, and credentials stay local and out of Git.

## Context7

The files under `config/context7/` are examples, not active connections.
Merge the appropriate example with your existing client configuration:

- **Codex:** merge `codex-config.toml.example` into your local `.codex/config.toml`
  for this trusted checkout, or your user configuration. Set `CONTEXT7_API_KEY`
  through your local secret manager/environment before launching the client.
- **MCP clients using `.mcp.json`:** merge `mcp.json.example` into your project
  configuration. It uses Context7's OAuth endpoint; complete authentication in
  the client's MCP settings. Do not replace an existing configuration wholesale.

Restart/reload the client, confirm Context7 is connected, and resolve **pygame-ce**
and **ModernGL** by name using `resolve-library-id`. Check the returned source and
available versions against `pyproject.toml` and the installed environment; then
use `query-docs` with the returned ID and a specific API question. A successful
connection does not prove coverage of a particular package or version. Use the
official package docs when matching coverage is unavailable. Keep retrieved
documentation separate from WORLDSEED's own architectural decisions.

No authentication, library-coverage check, or desktop activation is claimed by
checking in these files. Official setup references:
[Context7 clients](https://context7.com/docs/resources/all-clients),
[OAuth](https://context7.com/docs/howto/oauth), and
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).
