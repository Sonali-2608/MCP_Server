# Expense Tracker MCP Server

This project is a lightweight FastMCP server for managing personal expenses and budgets over HTTP. It provides a simple way to store expenses in a local SQLite database, organize them by category, and query spending information through MCP-compatible tools.

### What it does

- Tracks expense entries with amounts, dates, and descriptions
- Supports category-based organization using a JSON category list
- Exposes expense-related operations through an MCP server endpoint
- Can be run locally for development or deployed remotely for HTTP access

## Run locally

```powershell
uv run main.py
```

The local MCP endpoint is:

```text
http://localhost:8000/mcp
```

## Remote deployment

This project is already configured for a remote HTTP MCP server:

```python
mcp.run(transport="http", host="0.0.0.0", port=port)
```

The server reads these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Network interface to bind |
| `PORT` | `8000` | HTTP port, usually set by the hosting provider |
| `EXPENSE_DB_PATH` | `./expenses.db` | SQLite database path |
| `EXPENSE_CATEGORIES_PATH` | `./categories.json` | Categories JSON path |

Typical remote start command:

```powershell
uv run main.py
```

After deployment, connect your MCP client to:

```text
https://your-domain.example/mcp
```

## Important remote notes

- Use HTTPS for public access.
- Make sure the hosting provider exposes the assigned `PORT`.
- If you keep SQLite, configure persistent storage and set `EXPENSE_DB_PATH`
  to that mounted path. Otherwise the database may reset after redeploys.
- For a public server, add authentication or place it behind a protected
  gateway before storing real financial data.
