# Expense Tracker MCP Server

FastMCP server for tracking expenses and budgets over HTTP.

## Run locally

```powershell
uv run main.py
```

The local MCP endpoint is:

```text
http://localhost:8000/mcp
```

Do not use `http://0.0.0.0:8000/mcp` in a browser or MCP client. `0.0.0.0`
is only the server bind address.

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
