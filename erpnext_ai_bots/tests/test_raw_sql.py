"""Tests for raw_sql query validation, table blocklists, and column masking."""
import unittest
import sys
import os
from unittest.mock import MagicMock

# Setup sys.path and mock frappe if not installed
app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

if "frappe" not in sys.modules:
    mock_frappe = MagicMock()
    mock_frappe._ = lambda x: x
    sys.modules["frappe"] = mock_frappe

# Import raw_sql validator functions
from erpnext_ai_bots.tools.core.raw_sql import (
    _validate_select_only,
    _mask_sensitive_columns,
)


class TestRawSQLSecurity(unittest.TestCase):

    def test_valid_select_allowed(self):
        """Standard SELECT queries on business tables should pass validation."""
        valid_queries = [
            "SELECT name, customer_name FROM `tabCustomer` LIMIT 10",
            "SELECT item_code, stock_qty FROM `tabBin` WHERE stock_qty > 0",
            "SELECT count(*) FROM `tabSales Invoice` WHERE docstatus = 1;",
        ]
        for query in valid_queries:
            try:
                _validate_select_only(query)
            except ValueError as e:
                self.fail(f"Valid query was rejected: {query} with error: {e}")

    def test_non_select_rejected(self):
        """Non-SELECT queries must be rejected."""
        mutations = [
            "INSERT INTO `tabCustomer` (name) VALUES ('Test')",
            "UPDATE `tabItem` SET standard_rate = 100",
            "DELETE FROM `tabCustomer` WHERE name = 'Test'",
            "DROP TABLE `tabBin`",
            "ALTER TABLE `tabCustomer` ADD COLUMN test_col VARCHAR(10)",
            "TRUNCATE TABLE `tabSales Order`",
        ]
        for q in mutations:
            with self.assertRaises(ValueError, msg=f"Should reject: {q}"):
                _validate_select_only(q)

    def test_multi_statement_rejected(self):
        """Semicolons chaining multiple statements must be rejected."""
        injections = [
            "SELECT 1; DROP TABLE `tabCustomer`",
            "SELECT * FROM `tabItem`; UPDATE `tabCustomer` SET name = 'x';",
        ]
        for q in injections:
            with self.assertRaises(ValueError, msg=f"Should reject chained query: {q}"):
                _validate_select_only(q)

    def test_system_schemas_blocked(self):
        """Queries accessing information_schema, mysql, etc. must be rejected."""
        schema_queries = [
            "SELECT table_name FROM information_schema.tables",
            "SELECT user, host FROM mysql.user",
            "SELECT * FROM performance_schema.threads",
            "SELECT * FROM sys.version",
        ]
        for q in schema_queries:
            with self.assertRaises(ValueError, msg=f"Should reject system schema: {q}"):
                _validate_select_only(q)

    def test_sensitive_tables_blocked(self):
        """Access to __Auth, tabUser, tabSingles, sessions, and tokens must be blocked."""
        forbidden_table_queries = [
            "SELECT * FROM `__Auth`",
            "SELECT * FROM __auth",
            "SELECT password, api_secret FROM `tabUser`",
            "SELECT * FROM tabUser",
            "SELECT * FROM `tabSingles` WHERE doctype = 'System Settings'",
            "SELECT * FROM `tabSessions`",
            "SELECT * FROM `tabAI OpenAI Token`",
            "SELECT * FROM `tabOAuth Bearer Token`",
            "SELECT * FROM `tabConnected App`",
        ]
        for q in forbidden_table_queries:
            with self.assertRaises(ValueError, msg=f"Should reject sensitive table: {q}"):
                _validate_select_only(q)

    def test_malicious_functions_blocked(self):
        """Side-channel functions (SLEEP, BENCHMARK, LOAD_FILE, OUTFILE) must be blocked."""
        bad_functions = [
            "SELECT SLEEP(5)",
            "SELECT sleep(10) FROM `tabCustomer`",
            "SELECT BENCHMARK(1000000, MD5('test'))",
            "SELECT LOAD_FILE('/etc/passwd')",
            "SELECT * FROM `tabCustomer` INTO OUTFILE '/tmp/customers.csv'",
        ]
        for q in bad_functions:
            with self.assertRaises(ValueError, msg=f"Should reject dangerous function: {q}"):
                _validate_select_only(q)

    def test_mask_sensitive_columns(self):
        """Sensitive credential columns returned in rows must be masked."""
        rows = [
            {
                "name": "USR-0001",
                "email": "test@example.com",
                "password": "hashed_secret_password",
                "api_key": "abc123secret",
                "api_secret": "very_secret_key",
                "db_password": "rootpassword",
                "normal_field": "safe_value",
            }
        ]
        masked = _mask_sensitive_columns(rows)
        self.assertEqual(masked[0]["normal_field"], "safe_value")
        self.assertEqual(masked[0]["password"], "********")
        self.assertEqual(masked[0]["api_key"], "********")
        self.assertEqual(masked[0]["api_secret"], "********")
        self.assertEqual(masked[0]["db_password"], "********")


if __name__ == "__main__":
    unittest.main()
