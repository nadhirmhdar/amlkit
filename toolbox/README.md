# MCP Toolbox for AMLKit SQLite

Exposes read-only AMLKit database queries as MCP tools using
[Google's genai-toolbox](https://github.com/googleapis/genai-toolbox).

## Install

Download the `toolbox` binary for your platform from
[GitHub Releases](https://github.com/googleapis/genai-toolbox/releases).

Place it in this directory or anywhere on your PATH.

## Run

```bash
toolbox --tools_file=toolbox/tools.yaml
```

By default, connects to `data/aml.db`. Override with:

```bash
AMLKIT_DB_PATH=/path/to/your.db toolbox --tools_file=toolbox/tools.yaml
```

## Add to Claude Code (.mcp.json)

```json
{
  "mcpServers": {
    "amlkit-db": {
      "command": "toolbox",
      "args": ["--tools_file", "toolbox/tools.yaml"]
    }
  }
}
```

## Available tools

| Tool | Description |
|------|-------------|
| `search_customers` | Search customers by name (LIKE match), scoped to one `org_id` |
| `get_alerts` | Get screening alerts for a customer, scoped to one `org_id` |
| `get_screenings` | Get screening history for a customer, scoped to one `org_id` |
| `list_datasets` | List all sanctions datasets with refresh status (shared reference data, not org-scoped) |

`search_customers`, `get_alerts` and `get_screenings` all require an
`org_id` argument -- every row they touch belongs to exactly one
organization, so a caller must always state which one it is asking about.
There is no default or "all organizations" mode.
