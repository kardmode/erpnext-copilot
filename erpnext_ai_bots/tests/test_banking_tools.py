"""Tests for Banking & Reconciliation Tools (Mint / ERPNext integration)."""
import unittest
import sys
import os
import types
from datetime import datetime, timedelta

app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

if "frappe" not in sys.modules or not hasattr(sys.modules["frappe"], "__path__"):
    mock_frappe = types.ModuleType("frappe")
    mock_frappe._ = lambda x: x
    mock_frappe.__path__ = []
    sys.modules["frappe"] = mock_frappe

if "frappe.utils" not in sys.modules:
    mock_utils = types.ModuleType("frappe.utils")
    mock_utils.now_datetime = datetime.now
    mock_utils.add_to_date = lambda dt, **kwargs: dt + timedelta(**kwargs)
    sys.modules["frappe.utils"] = mock_utils

from erpnext_ai_bots.tools.registry import ToolRegistry, TOOL_MAP
from erpnext_ai_bots.guards.permissions import TOOL_PERMISSION_MAP
from erpnext_ai_bots.guards.hitl import HITLGuard
from erpnext_ai_bots.tools.banking.unreconciled_transactions import GetUnreconciledTransactionsTool
from erpnext_ai_bots.tools.banking.suggest_matches import SuggestMatchesTool
from erpnext_ai_bots.tools.banking.reconcile_voucher import ReconcileVoucherTool
from erpnext_ai_bots.tools.banking.auto_reconcile import AutoReconcileTool


class TestBankingTools(unittest.TestCase):

    def test_banking_tools_registered_in_tool_map(self):
        """All 4 banking tools must be present in canonical TOOL_MAP."""
        banking_keys = [
            "banking.get_unreconciled_transactions",
            "banking.suggest_matches",
            "banking.reconcile_voucher",
            "banking.auto_reconcile",
        ]
        for key in banking_keys:
            self.assertIn(key, TOOL_MAP)

    def test_banking_tools_have_permissions(self):
        """All banking tools must have permissions defined in TOOL_PERMISSION_MAP."""
        self.assertEqual(
            TOOL_PERMISSION_MAP.get("banking.get_unreconciled_transactions"),
            ("read", "Bank Transaction"),
        )
        self.assertEqual(
            TOOL_PERMISSION_MAP.get("banking.suggest_matches"),
            ("read", "Bank Transaction"),
        )
        self.assertEqual(
            TOOL_PERMISSION_MAP.get("banking.reconcile_voucher"),
            ("write", "Bank Transaction"),
        )
        self.assertEqual(
            TOOL_PERMISSION_MAP.get("banking.auto_reconcile"),
            ("write", "Bank Transaction"),
        )

    def test_reconcile_requires_hitl_approval(self):
        """reconcile_voucher and auto_reconcile MUST require human approval."""
        guard = HITLGuard(user="accountant@example.com", session_id="SESS-001", company="Acme")

        # reconcile_voucher
        needs_app, act_type, summary = guard.requires_approval(
            "banking.reconcile_voucher",
            {"bank_transaction": "BT-2026-00001", "vouchers": [{"payment_name": "ACC-PAY-001"}]},
            action_type="Update",
        )
        self.assertTrue(needs_app)
        self.assertIn("BT-2026-00001", summary)

        # auto_reconcile
        needs_app_auto, act_type_auto, summary_auto = guard.requires_approval(
            "banking.auto_reconcile",
            {"bank_account": "Operating Account - Acme"},
            action_type="Update",
        )
        self.assertTrue(needs_app_auto)
        self.assertIn("Operating Account - Acme", summary_auto)

    def test_banking_tool_schemas(self):
        """Verify schema properties and action_types."""
        t1 = GetUnreconciledTransactionsTool(user="test", company="Acme")
        self.assertEqual(t1.action_type, "Read")
        self.assertEqual(t1.schema()["name"], "banking.get_unreconciled_transactions")

        t2 = SuggestMatchesTool(user="test", company="Acme")
        self.assertEqual(t2.action_type, "Read")
        self.assertIn("bank_transaction", t2.schema()["input_schema"]["properties"])

        t3 = ReconcileVoucherTool(user="test", company="Acme")
        self.assertEqual(t3.action_type, "Update")
        self.assertIn("vouchers", t3.schema()["input_schema"]["properties"])

        t4 = AutoReconcileTool(user="test", company="Acme")
        self.assertEqual(t4.action_type, "Update")
        self.assertIn("bank_account", t4.schema()["input_schema"]["properties"])

    def test_banking_category_routing(self):
        """Banking queries should route to Banking tools and exclude HR tools."""
        registry = ToolRegistry(user="admin@example.com", company="Acme")
        active = registry.resolve_active_tools(category="Banking")

        self.assertIn("banking.get_unreconciled_transactions", active)
        self.assertIn("banking.suggest_matches", active)
        self.assertIn("banking.reconcile_voucher", active)
        self.assertIn("banking.auto_reconcile", active)
        self.assertNotIn("hr.get_salary_slip", active)
        self.assertNotIn("stock.create_item", active)


if __name__ == "__main__":
    unittest.main()
