"""Tests for Human-in-the-Loop (HITL) Guard and Pending Action enforcement."""
import unittest
import sys
import os
import types
from datetime import datetime, timedelta

# Setup sys.path and mock frappe if not installed
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

from erpnext_ai_bots.guards.hitl import HITLGuard


class TestHITLGuard(unittest.TestCase):

    def setUp(self):
        self.guard = HITLGuard(user="test@example.com", session_id="AI-SESS-00001", company="Test Corp")

    def test_read_operations_bypass_hitl(self):
        """Read-only and report tools must not be blocked by HITL."""
        read_tools = [
            ("core.get_list", {"doctype": "Sales Invoice"}),
            ("core.get_document", {"doctype": "Customer", "name": "CUST-001"}),
            ("accounting.get_trial_balance", {}),
            ("stock.get_stock_balance", {"item_code": "ITEM-001"}),
        ]
        for tool, inp in read_tools:
            needs_approval, action_type, summary = self.guard.requires_approval(
                tool, inp, action_type="Read"
            )
            self.assertFalse(needs_approval, f"{tool} should not require approval")

    def test_submit_requires_hitl(self):
        """SubmitDocumentTool MUST require explicit human approval."""
        needs_approval, action_type, summary = self.guard.requires_approval(
            "core.submit_document",
            {"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00001"},
            action_type="Submit",
        )
        self.assertTrue(needs_approval, "Submit document must require approval")
        self.assertEqual(action_type, "Submit")
        self.assertIn("Submit Sales Invoice 'ACC-SINV-2026-00001'", summary)

    def test_financial_entries_require_hitl(self):
        """Journal Entry and Payment Entry creation MUST require human approval."""
        # Journal Entry
        needs_approval, action_type, summary = self.guard.requires_approval(
            "accounting.create_journal_entry",
            {"voucher_type": "Bank Entry", "accounts": []},
            action_type="Create",
        )
        self.assertTrue(needs_approval, "Journal Entry must require approval")
        self.assertIn("Bank Entry", summary)

        # Payment Entry
        needs_approval, action_type, summary = self.guard.requires_approval(
            "accounting.create_payment_entry",
            {"party": "Acme Supplier", "paid_amount": 5000},
            action_type="Create",
        )
        self.assertTrue(needs_approval, "Payment Entry must require approval")
        self.assertIn("Acme Supplier", summary)
        self.assertIn("5000", summary)

    def test_cancel_and_delete_require_hitl(self):
        """Cancel and Delete actions MUST require human approval."""
        needs_approval, action_type, summary = self.guard.requires_approval(
            "core.cancel_document",
            {"doctype": "Sales Order", "name": "SO-001"},
            action_type="Cancel",
        )
        self.assertTrue(needs_approval, "Cancel must require approval")
        self.assertEqual(action_type, "Cancel")


if __name__ == "__main__":
    unittest.main()
