from typing import Any, Dict
import frappe
from erpnext_ai_bots.tools.base import BaseTool


class AutoReconcileTool(BaseTool):
    name = "banking.auto_reconcile"
    description = (
        "Execute automated batch reconciliation for a Bank Account. "
        "Finds and links all exact 1:1 matches between unallocated Bank Transactions and posted vouchers."
    )
    parameters = {
        "bank_account": {
            "type": "string",
            "description": "Name of the Bank Account (e.g. 'Checking Account - Acme')",
        },
    }
    required_params = ["bank_account"]
    action_type = "Update"
    required_doctype = "Bank Transaction"
    required_ptype = "write"

    def execute(self, bank_account: str, **kwargs) -> Dict[str, Any]:
        frappe.has_permission("Bank Transaction", ptype="write", throw=True)

        if not frappe.db.exists("Bank Account", bank_account):
            return {"error": f"Bank Account '{bank_account}' does not exist."}

        # Try Mint auto-reconciler first, then fall back to ERPNext
        try:
            from mint.apis.bank_reconciliation import auto_reconcile_vouchers as mint_auto_reconcile
            summary = mint_auto_reconcile(bank_account)
            return {
                "status": "success",
                "bank_account": bank_account,
                "reconciled_count": summary.get("reconciled", 0),
                "total_reconciled_amount": summary.get("total_amount", 0.0),
                "remaining_unreconciled": summary.get("remaining", 0),
                "engine": "Mint High-Volume Engine",
                "message": summary.get("message") or f"Auto-reconciled {summary.get('reconciled', 0)} transactions.",
            }
        except Exception:
            try:
                from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
                    auto_reconcile_vouchers as erpnext_auto_reconcile,
                )
                res = erpnext_auto_reconcile(bank_account)
                return {
                    "status": "success",
                    "bank_account": bank_account,
                    "result": res,
                    "engine": "ERPNext Standard Engine",
                    "message": f"Auto-reconciliation job executed for '{bank_account}'.",
                }
            except Exception as e:
                frappe.log_error(title="Auto Reconcile Error", message=frappe.get_traceback())
                return {"error": f"Auto-reconciliation failed: {str(e)}"}
