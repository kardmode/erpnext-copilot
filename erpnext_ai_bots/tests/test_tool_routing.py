"""Tests for Category-based Dynamic Tool Routing and Schema Scoping."""
import unittest
import sys
import os
import types

app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

if "frappe" not in sys.modules or not hasattr(sys.modules["frappe"], "__path__"):
    mock_frappe = types.ModuleType("frappe")
    mock_frappe._ = lambda x: x
    mock_frappe.__path__ = []
    sys.modules["frappe"] = mock_frappe

def _mock_roles(user):
    if user == "admin@example.com":
        return ["System Manager", "Accounts Manager"]
    elif user == "accountant@example.com":
        return ["Accounts User"]
    elif user == "employee@example.com":
        return ["Employee"]
    return []

sys.modules["frappe"].get_roles = _mock_roles

from erpnext_ai_bots.tools.registry import (
    ToolRegistry,
    CORE_TOOLS,
    CATEGORY_TOOL_MAP,
)


class TestDynamicToolRouting(unittest.TestCase):

    def test_finance_category_scoping(self):
        """Finance category must load Core + Finance tools and exclude unrelated HR tools."""
        registry = ToolRegistry(user="admin@example.com", company="Test Corp")
        active = registry.resolve_active_tools(category="Finance")

        # Core tools must be present
        self.assertIn("core.get_list", active)
        self.assertIn("core.create_document", active)

        # Finance tools must be present
        self.assertIn("accounting.get_trial_balance", active)
        self.assertIn("accounting.get_bank_balances", active)
        self.assertIn("accounting.create_journal_entry", active)

        # Unrelated domain tools must be excluded
        self.assertNotIn("hr.get_salary_slip", active)
        self.assertNotIn("hr.get_leave_balance", active)
        self.assertNotIn("sales.create_quotation", active)

        # Count should be substantially smaller than total (55)
        self.assertLess(len(active), 30)

    def test_hr_category_scoping(self):
        """HR category must load Core + HR tools and exclude Stock/Sales/Finance."""
        registry = ToolRegistry(user="admin@example.com", company="Test Corp")
        active = registry.resolve_active_tools(category="HR")

        self.assertIn("hr.get_leave_balance", active)
        self.assertIn("hr.get_salary_slip", active)
        self.assertNotIn("stock.create_stock_entry", active)
        self.assertNotIn("sales.create_customer", active)
        self.assertNotIn("accounting.create_journal_entry", active)

    def test_dynamic_keyword_intent_detection(self):
        """A General category message with HR keywords should automatically include HR tools."""
        registry = ToolRegistry(user="admin@example.com", company="Test Corp")

        # User asks about employee salary slip in General chat
        active = registry.resolve_active_tools(
            category="General",
            message_text="Can you check the salary slip and leave balance for employee EMP-001?",
        )
        self.assertIn("hr.get_salary_slip", active)
        self.assertIn("hr.get_leave_balance", active)

        # User asks about invoices in General chat
        active_fin = registry.resolve_active_tools(
            category="General",
            message_text="Show me all overdue invoices and our current bank balance",
        )
        self.assertIn("accounting.get_outstanding_invoices", active_fin)
        self.assertIn("accounting.get_bank_balances", active_fin)

    def test_role_filtering_raw_sql(self):
        """Non-System Manager users must NOT have core.raw_sql in active tools."""
        employee_registry = ToolRegistry(user="employee@example.com", company="Test Corp")
        emp_active = employee_registry.resolve_active_tools(category="General")
        self.assertNotIn("core.raw_sql", emp_active)

        admin_registry = ToolRegistry(user="admin@example.com", company="Test Corp")
        admin_active = admin_registry.resolve_active_tools(category="General")
        self.assertIn("core.raw_sql", admin_active)

    def test_management_tools_filtered_for_regular_users(self):
        """Management-only analytics tools must be excluded for non-managers."""
        accountant_registry = ToolRegistry(user="accountant@example.com", company="Test Corp")
        tools = accountant_registry.resolve_active_tools(category="Finance")

        # Accounts User can get invoices and account balance
        self.assertIn("accounting.get_outstanding_invoices", tools)
        self.assertIn("accounting.get_account_balance", tools)

        # But management tools like profit_and_loss or gross_margin are excluded
        self.assertNotIn("accounting.get_gross_margin", tools)
        self.assertNotIn("accounting.get_profit_and_loss", tools)


if __name__ == "__main__":
    unittest.main()
