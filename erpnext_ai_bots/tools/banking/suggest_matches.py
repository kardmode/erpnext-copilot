from typing import Any, Dict, List
import frappe
from erpnext_ai_bots.tools.base import BaseTool


class SuggestMatchesTool(BaseTool):
    name = "banking.suggest_matches"
    description = (
        "Find matching accounting vouchers (Payment Entries, Journal Entries, Sales & Purchase Invoices) "
        "for an unallocated Bank Transaction using reference numbers, party details, and transaction amounts."
    )
    parameters = {
        "bank_transaction": {
            "type": "string",
            "description": "Name of the Bank Transaction document (e.g. 'BT-2026-00001')",
        },
    }
    required_params = ["bank_transaction"]
    action_type = "Read"
    required_doctype = "Bank Transaction"
    required_ptype = "read"

    def execute(self, bank_transaction: str, **kwargs) -> Dict[str, Any]:
        frappe.has_permission("Bank Transaction", ptype="read", throw=True)

        if not frappe.db.exists("Bank Transaction", bank_transaction):
            return {"error": f"Bank Transaction '{bank_transaction}' does not exist."}

        bt = frappe.get_doc("Bank Transaction", bank_transaction)
        unallocated = float(bt.unallocated_amount or 0)
        ref_no = (bt.reference_number or "").strip()
        party = (bt.party or "").strip()

        # Try Mint reconciliation engine first, then fall back to standard ERPNext
        raw_vouchers: List[Dict[str, Any]] = []
        source = "ERPNext"
        try:
            from mint.apis.bank_reconciliation import get_linked_payments as mint_get_linked
            raw_vouchers = mint_get_linked(bank_transaction) or []
            source = "Mint"
        except Exception:
            try:
                from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
                    get_linked_payments as erpnext_get_linked,
                )
                raw_vouchers = erpnext_get_linked(bank_transaction) or []
                source = "ERPNext"
            except Exception as e:
                frappe.log_error(title="Banking Suggest Matches Error", message=frappe.get_traceback())

        formatted_matches = []
        for v in raw_vouchers:
            v_amount = float(v.get("paid_amount") or v.get("amount") or v.get("total_debit") or v.get("total_credit") or 0)
            v_ref = str(v.get("reference_no") or v.get("cheque_number") or "").strip()
            v_party = str(v.get("party") or "").strip()

            reasons = []
            confidence = "Medium"
            if ref_no and v_ref and ref_no.lower() == v_ref.lower():
                reasons.append("Exact Reference Match")
                confidence = "High"
            if abs(v_amount - unallocated) < 0.001:
                reasons.append("Exact Amount Match")
                if confidence != "High":
                    confidence = "High"
            if party and v_party and party.lower() == v_party.lower():
                reasons.append("Party Match")

            formatted_matches.append({
                "doctype": v.get("doctype") or v.get("payment_doctype"),
                "name": v.get("name") or v.get("payment_name"),
                "posting_date": v.get("posting_date"),
                "amount": v_amount,
                "party": v_party,
                "reference_no": v_ref,
                "confidence": confidence,
                "match_reasons": reasons,
            })

        return {
            "bank_transaction": {
                "name": bt.name,
                "date": bt.date,
                "bank_account": bt.bank_account,
                "unallocated_amount": unallocated,
                "deposit": float(bt.deposit or 0),
                "withdrawal": float(bt.withdrawal or 0),
                "reference_number": ref_no,
                "party": party,
                "description": bt.description,
            },
            "matched_vouchers": formatted_matches,
            "match_count": len(formatted_matches),
            "engine": source,
        }
