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
| `search_customers` | Search customers by name (LIKE match) |
| `get_alerts` | Get screening alerts for a customer |
| `get_screenings` | Get screening history for a customer |
| `list_datasets` | List all sanctions datasets with refresh status |
