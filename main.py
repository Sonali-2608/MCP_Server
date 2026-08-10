from fastmcp import FastMCP
import json
import os
import sqlite3
import tempfile

BASE_DIR = os.path.dirname(__file__)
CONFIGURED_DB_PATH = os.getenv("EXPENSE_DB_PATH")
DB_PATH = CONFIGURED_DB_PATH or os.path.join(BASE_DIR, "expenses.db")
CATEGORIES_PATH = os.getenv("EXPENSE_CATEGORIES_PATH", os.path.join(BASE_DIR, "categories.json"))
LEGACY_CATEGORIES_PATH = os.path.join(BASE_DIR, "categoreis.json")

mcp = FastMCP("ExpenseTracker")

def candidate_db_paths():
    paths = [DB_PATH]

    if not CONFIGURED_DB_PATH:
        fastmcp_home = os.getenv("FASTMCP_HOME")
        if fastmcp_home:
            paths.append(os.path.join(fastmcp_home, "expense-tracker", "expenses.db"))

        paths.append(os.path.join(tempfile.gettempdir(), "expense-tracker", "expenses.db"))

    seen = set()
    for path in paths:
        absolute_path = os.path.abspath(path)
        if absolute_path not in seen:
            seen.add(absolute_path)
            yield absolute_path

async def init_db():
    global DB_PATH

    errors = []
    for path in candidate_db_paths():
        try:
            db_dir = os.path.dirname(path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            with sqlite3.connect(path) as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS expenses(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        amount REAL NOT NULL,
                        category TEXT NOT NULL,
                        subcategory TEXT DEFAULT '',
                        note TEXT DEFAULT ''
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS budgets(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_date TEXT NOT NULL,
                        end_date TEXT NOT NULL,
                        amount REAL NOT NULL,
                        category TEXT DEFAULT '',
                        note TEXT DEFAULT '',
                        UNIQUE(start_date, end_date, category)
                    )
                """)

            DB_PATH = path
            return
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    suggestions = (
        "Set EXPENSE_DB_PATH to a writable persistent path in your deployment, "
        "or use an external database for production persistence."
    )
    raise RuntimeError(f"Failed to initialize database. Tried {errors}. {suggestions}")

@mcp.tool()
async def database_status():
    '''Check whether the expense database can be initialized and written to.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA user_version")
        return {
            "status": "ok",
            "db_path": DB_PATH,
            "configured_by_env": CONFIGURED_DB_PATH is not None,
            "persistent_storage_note": (
                "If this path is under a temp directory, data can disappear after the cloud server restarts. "
                "Set EXPENSE_DB_PATH to persistent storage for real use."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = ""):
    '''Add a new expense entry to the database.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            return {"status": "ok", "id": cur.lastrowid}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def edit_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str | None = None,
    note: str | None = None,
    new_date: str | None = None,
    new_amount: float | None = None,
    new_category: str | None = None,
    new_subcategory: str | None = None,
    new_note: str | None = None,
):
    '''Edit one expense matching date, amount, category, and optional details.'''
    try:
        await init_db()
        updates = {}
        for field, value in {
            "date": new_date,
            "amount": new_amount,
            "category": new_category,
            "subcategory": new_subcategory,
            "note": new_note,
        }.items():
            if value is not None:
                updates[field] = value

        if not updates:
            return {"status": "error", "message": "Provide at least one field to update."}

        match_query = """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date = ? AND amount = ? AND category = ?
        """
        match_params = [date, amount, category]

        if subcategory is not None:
            match_query += " AND subcategory = ?"
            match_params.append(subcategory)

        if note is not None:
            match_query += " AND note = ?"
            match_params.append(note)

        set_clause = ", ".join(f"{field} = ?" for field in updates)

        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(match_query, match_params)
            cols = [d[0] for d in cur.description]
            matches = [dict(zip(cols, r)) for r in cur.fetchall()]

            if not matches:
                return {"status": "error", "message": "No matching expense was found."}

            if len(matches) > 1:
                return {
                    "status": "error",
                    "message": "Multiple matching expenses were found. Provide subcategory or note to narrow it down.",
                    "matches": matches,
                }

            expense_id = matches[0]["id"]
            c.execute(f"UPDATE expenses SET {set_clause} WHERE id = ?", list(updates.values()) + [expense_id])
            return {"status": "ok", "updated_expense": {**matches[0], **updates}}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def delete_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str | None = None,
    note: str | None = None,
):
    '''Delete one expense matching date, amount, category, and optional details.'''
    try:
        await init_db()
        query = """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date = ? AND amount = ? AND category = ?
        """
        params = [date, amount, category]

        if subcategory is not None:
            query += " AND subcategory = ?"
            params.append(subcategory)

        if note is not None:
            query += " AND note = ?"
            params.append(note)

        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            matches = [dict(zip(cols, r)) for r in cur.fetchall()]

            if not matches:
                return {"status": "error", "message": "No matching expense was found."}

            if len(matches) > 1:
                return {
                    "status": "error",
                    "message": "Multiple matching expenses were found. Use delete_expense_by_id instead.",
                    "matches": matches,
                }

            expense_id = matches[0]["id"]
            c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            return {"status": "ok", "deleted_expense": matches[0]}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def delete_expense_by_id(expense_id: int):
    '''Delete one expense by its id.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE id = ?
                """,
                (expense_id,),
            )
            row = cur.fetchone()

            if row is None:
                return {"status": "error", "message": "No matching expense was found."}

            cols = [d[0] for d in cur.description]
            deleted_expense = dict(zip(cols, row))
            c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            return {"status": "ok", "deleted_expense": deleted_expense}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    
@mcp.tool()
async def list_expenses(start_date: str | None = None, end_date: str | None = None):
    '''List expense entries, optionally within an inclusive date range.'''
    try:
        await init_db()
        query = """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE 1 = 1
        """
        params = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date DESC, id DESC"

        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str | None = None):
    '''Summarize expenses by category within an inclusive date range.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            query = (
                """
                SELECT category, SUM(amount) AS total_amount
                FROM expenses
                WHERE date BETWEEN ? AND ?
                """
            )
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY category ASC"

            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def set_budget(start_date: str, end_date: str, amount: float, category: str = "", note: str = ""):
    '''Create or update a budget for a date range and optional category.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                """
                INSERT INTO budgets(start_date, end_date, amount, category, note)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(start_date, end_date, category)
                DO UPDATE SET amount = excluded.amount, note = excluded.note
                """,
                (start_date, end_date, amount, category, note)
            )
            budget_id = c.execute(
                """
                SELECT id FROM budgets
                WHERE start_date = ? AND end_date = ? AND category = ?
                """,
                (start_date, end_date, category)
            ).fetchone()[0]
            return {
                "status": "ok",
                "id": budget_id,
                "start_date": start_date,
                "end_date": end_date,
                "amount": amount,
                "category": category,
            }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def list_budgets(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
):
    '''List budgets, optionally filtered by overlapping date range and category.'''
    try:
        await init_db()
        query = """
            SELECT id, start_date, end_date, amount, category, note
            FROM budgets
            WHERE 1 = 1
        """
        params = []

        if start_date:
            query += " AND end_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND start_date <= ?"
            params.append(end_date)

        if category is not None:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY start_date ASC, end_date ASC, category ASC"

        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def delete_budget(start_date: str, end_date: str, category: str = ""):
    '''Delete a budget matching date range and optional category.'''
    try:
        await init_db()
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "DELETE FROM budgets WHERE start_date = ? AND end_date = ? AND category = ?",
                (start_date, end_date, category),
            )
            if cur.rowcount == 0:
                return {"status": "error", "message": "No matching budget was found."}
            return {
                "status": "ok",
                "deleted_budget": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "category": category,
                },
            }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.tool()
async def budget_status(start_date: str, end_date: str, category: str | None = None):
    '''Compare spending against budgets within an inclusive date range.'''
    try:
        await init_db()
        budget_query = """
            SELECT id, start_date, end_date, amount, category, note
            FROM budgets
            WHERE start_date <= ? AND end_date >= ?
        """
        budget_params = [end_date, start_date]

        if category is not None:
            budget_query += " AND category = ?"
            budget_params.append(category)

        budget_query += " ORDER BY start_date ASC, end_date ASC, category ASC"

        with sqlite3.connect(DB_PATH) as c:
            budgets_cur = c.execute(budget_query, budget_params)
            budget_cols = [d[0] for d in budgets_cur.description]
            budgets = [dict(zip(budget_cols, r)) for r in budgets_cur.fetchall()]

            statuses = []
            for budget in budgets:
                spend_query = """
                    SELECT COALESCE(SUM(amount), 0)
                    FROM expenses
                    WHERE date BETWEEN ? AND ?
                """
                spend_params = [
                    max(start_date, budget["start_date"]),
                    min(end_date, budget["end_date"]),
                ]

                if budget["category"]:
                    spend_query += " AND category = ?"
                    spend_params.append(budget["category"])

                spent = c.execute(spend_query, spend_params).fetchone()[0]
                remaining = budget["amount"] - spent
                statuses.append({
                    **budget,
                    "spent": spent,
                    "remaining": remaining,
                    "over_budget": remaining < 0,
                })

            return statuses
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@mcp.resource("expense://categories", mime_type="application/json")
async def categories():
    # Read fresh each time so you can edit the file without restarting
    try:
        path = CATEGORIES_PATH if os.path.exists(CATEGORIES_PATH) else LEGACY_CATEGORIES_PATH
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORT", "8000"))
    except ValueError:
        port = 8000
    mcp.run(transport="http", host=host, port=port)
