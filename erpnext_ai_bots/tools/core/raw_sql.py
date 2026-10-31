import re
from typing import Any, Dict, List

import frappe
from erpnext_ai_bots.tools.base import BaseTool

# Forbidden statement keywords anywhere in the statement outside of string literals
_FORBIDDEN_MUTATION_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|RENAME"
    r"|GRANT|REVOKE|LOCK|UNLOCK|CALL|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

# Forbidden administrative/internal schemas
_FORBIDDEN_SCHEMAS = re.compile(
    r"\b(information_schema|performance_schema|mysql|sys)\b",
    re.IGNORECASE,
)

# Forbidden sensitive system and credential tables
_FORBIDDEN_TABLES = re.compile(
    r"[`'\"]?\b(__auth|tabuser|tabsingles|tabsessions|taboauth[_\s\w]*|"
    r"tabai[_\s\w]*token|tabsocial[_\s\w]*key|tabconnected[_\s\w]*app|"
    r"tabintegration[_\s\w]*request|tabaccess[_\s\w]*log|tabactivity[_\s\w]*log)\b[`'\"]?",
    re.IGNORECASE,
)

# Potentially malicious or side-channel functions
_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(SLEEP|BENCHMARK|LOAD_FILE)\s*\(|"
    r"\b(INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)

# Column names containing sensitive credentials that must be redacted from query results
_SENSITIVE_FIELD_NAMES = {
    "password", "api_secret", "api_key", "secret", "auth_token",
    "token", "access_token", "refresh_token", "reset_password_key",
    "verification_code", "private_key", "db_password", "oauth_token",
    "elevenlabs_api_key", "session_id", "sid", "authorization",
}


def _validate_select_only(query: str) -> None:
    """Raise ValueError if the query violates read-only or security policies."""
    stripped = query.strip()

    # 1. Block multi-statement queries (separated by semicolons)
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()

    if ";" in stripped:
        raise ValueError("Multi-statement queries (separated by ';') are strictly forbidden.")

    # 2. Must start with SELECT
    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError(
            "Only SELECT queries are allowed. "
            f"Your query starts with: {stripped[:40]!r}"
        )

    # 3. Block data-modifying SQL keywords
    if _FORBIDDEN_MUTATION_KEYWORDS.search(stripped):
        raise ValueError(
            "Query contains a forbidden keyword (INSERT/UPDATE/DELETE/DROP/etc.). "
            "Only read-only SELECT statements are permitted."
        )

    # 4. Block system/schema queries
    if _FORBIDDEN_SCHEMAS.search(stripped):
        raise ValueError(
            "Access to system schemas (information_schema, performance_schema, mysql, sys) is prohibited."
        )

    # 5. Block sensitive credential and authentication tables
    if _FORBIDDEN_TABLES.search(stripped):
        raise ValueError(
            "Access to sensitive authentication, user, or session tables is strictly prohibited in raw SQL."
        )

    # 6. Block malicious side-channel and file I/O functions
    if _FORBIDDEN_FUNCTIONS.search(stripped):
        raise ValueError("Use of SLEEP, BENCHMARK, LOAD_FILE, or INTO OUTFILE is prohibited.")


def _mask_sensitive_columns(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mask any sensitive credential or auth keys returned in query rows."""
    if not rows:
        return rows

    for row in rows:
        for key in list(row.keys()):
            key_lower = key.lower()
            if (
                key_lower in _SENSITIVE_FIELD_NAMES
                or any(key_lower.endswith(sfx) for sfx in ("_password", "_secret", "_token", "_key"))
            ):
                row[key] = "********"
    return rows


def _execute_with_custom_db(query: str, limit: int) -> list:
    """Run query via a direct pymysql connection using credentials from AI Bot Settings."""
    try:
        import pymysql  # noqa: PLC0415 — optional dependency
    except ImportError as exc:
        raise RuntimeError(
            "pymysql is not installed. Add `pymysql` to requirements.txt and "
            "run `bench pip install pymysql`."
        ) from exc

    settings = frappe.get_cached_doc("AI Bot Settings")
    conn = pymysql.connect(
        host=settings.db_host or "localhost",
        port=int(settings.db_port or 3306),
        user=settings.db_user,
        password=settings.get_password("db_password"),
        database=settings.db_name,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return list(cursor.fetchmany(limit))
    finally:
        conn.close()


def _execute_with_frappe_db(query: str, limit: int) -> list:
    """Run query through the existing Frappe DB connection (no extra credentials needed)."""
    # frappe.db.sql returns a list of dicts when as_dict=True
    rows = frappe.db.sql(query, as_dict=True)
    return rows[:limit]


class RawSQLTool(BaseTool):
    name = "core.raw_sql"
    description = (
        "Execute a read-only SQL SELECT query directly against the ERPNext MariaDB database. "
        "Use this for complex queries that need JOINs, GROUP BY, SUM, COUNT, etc. "
        "ERPNext table names are prefixed with 'tab' — e.g. `tabSales Invoice`, "
        "`tabCustomer`, `tabItem`, `tabPurchase Invoice`, `tabStock Ledger Entry`, "
        "`tabJournal Entry`, `tabEmployee`, `tabSalary Slip`, `tabBin` (stock levels), "
        "`tabTerritory`, `tabWarehouse`, `tabCompany`. "
        "Common fields: name (document ID), creation, modified, owner, docstatus "
        "(0=Draft, 1=Submitted, 2=Cancelled). "
        "ONLY SELECT queries are allowed. Max 100 rows returned."
    )
    parameters = {
        "query": {
            "type": "string",
            "description": (
                "The SQL SELECT query to execute. "
                "Always qualify table names with backticks when they contain spaces "
                "(e.g. `tabSales Invoice`). Always include a LIMIT clause."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Max rows to return (default 100, max 100).",
        },
    }
    required_params = ["query"]
    action_type = "Read"

    def execute(self, query: str, limit: int = 100, **kwargs) -> dict:
        limit = min(int(limit), 100)

        # Defense-in-depth: Enforce System Manager role requirement
        if self.user and self.user != "Administrator":
            try:
                roles = set(frappe.get_roles(self.user))
                if "System Manager" not in roles:
                    return {
                        "error": "Permission denied: core.raw_sql requires System Manager role.",
                        "rows": [],
                    }
            except Exception:
                pass

        try:
            _validate_select_only(query)
        except ValueError as exc:
            return {"error": str(exc), "rows": []}

        # Decide which execution path to use
        settings = frappe.get_cached_doc("AI Bot Settings")
        use_custom = bool(settings.db_user and settings.db_name)

        try:
            if use_custom:
                try:
                    rows = _execute_with_custom_db(query, limit)
                except Exception:
                    # Custom DB failed — fall back to Frappe's connection
                    rows = _execute_with_frappe_db(query, limit)
            else:
                rows = _execute_with_frappe_db(query, limit)
        except Exception as exc:
            frappe.log_error(
                title="core.raw_sql execution error",
                message=frappe.get_traceback(),
            )
            return {
                "error": f"Query failed: {type(exc).__name__}: {exc}",
                "rows": [],
            }

        sanitized_rows = _mask_sensitive_columns(rows)
        return {"rows": sanitized_rows, "count": len(sanitized_rows)}
