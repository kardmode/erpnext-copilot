from typing import Any, Dict, List
import json
import frappe
from erpnext_ai_bots.tools.base import BaseTool


class ReconcileVoucherTool(BaseTool):
    name = "banking.reconcile_voucher"
    description = (
        "Reconcile an unallocated Bank Transaction against one or more vouchers "
        "(Payment Entry, Journal Entry, Sales Invoice, Purchase Invoice). "
        "Allocates clearance amounts and updates the transaction status."
    )
    parameters = {
        "bank_transaction": {
            "type": "string",
            "description": "Name of the Bank Transaction document (e.g. 'BT-2026-00001')",
        },
        "vouchers": {
            "type": "array",
            "description": "List of vouchers to reconcile with allocated amounts",
            "items": {
                "type": "object",
                "properties": {
                    "payment_doctype": {
                        "type": "string",
                        "description": "DocType of the voucher (e.g. 'Payment Entry', 'Journal Entry', 'Sales Invoice')",
                    },
                    "payment_name": {
                        "type": "string",
                        "description": "Voucher document ID (e.g. 'ACC-PAY-2026-00012')",
                    },
                    "allocated_amount": {
                        "type": "number",
                        "description": "Amount to allocate to this voucher from the bank transaction",
                    },
                },
                "required": ["payment_doctype", "payment_name", "allocated_amount"],
            },
        },
    }
    required_params = ["bank_transaction", "vouchers"]
    action_type = "Update"
    required_doctype = "Bank Transaction"
    required_ptype = "write"

    def execute(self, bank_transaction: str, vouchers: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        frappe.has_permission("Bank Transaction", doc=bank_transaction, ptype="write", throw=True)

        if not frappe.db.exists("Bank Transaction", bank_transaction):
            return {"error": f"Bank Transaction '{bank_transaction}' not found."}

        # Normalize vouchers format
        normalized_vouchers = []
        for v in vouchers:
            normalized_vouchers.append({
                "payment_doctype": v.get("payment_doctype"),
                "payment_name": v.get("payment_name"),
                "allocated_amount": float(v.get("allocated_amount", 0)),
            })

        # Try Mint reconciliation engine first, then fall back to standard ERPNext
        try:
            from mint.apis.bank_reconciliation import reconcile_vouchers as mint_reconcile
            res = mint_reconcile(bank_transaction, normalized_vouchers)
        except Exception:
            try:
                from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
                    reconcile_vouchers as erpnext_reconcile,
                )
                res = erpnext_reconcile(bank_transaction, json.dumps(normalized_vouchers))
            except Exception as e:
                frappe.log_error(title="Banking Reconcile Voucher Error", message=frappe.get_traceback())
                return {"error": f"Failed to reconcile vouchers: {str(e)}"}

        # Refresh updated transaction
        bt = frappe.get_doc("Bank Transaction", bank_transaction)

        return {
            "status": "success",
            "bank_transaction": bt.name,
            "allocated_amount": float(bt.allocated_amount or 0),
            "unallocated_amount": float(bt.unallocated_amount or 0),
            "is_fully_reconciled": float(bt.unallocated_amount or 0) <= 0.001,
            "vouchers_reconciled": len(normalized_vouchers),
            "message": f"Bank Transaction '{bt.name}' successfully reconciled. Remaining unallocated: {bt.unallocated_amount}",
        }
