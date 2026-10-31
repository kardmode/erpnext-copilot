from typing import Any, Dict, Optional
import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetUnreconciledTransactionsTool(BaseTool):
    name = "banking.get_unreconciled_transactions"
    description = (
        "Retrieve unreconciled or partially allocated Bank Transactions for a bank account or company. "
        "Returns dates, amounts, reference numbers, parties, and unallocated amounts."
    )
    parameters = {
        "bank_account": {
            "type": "string",
            "description": "Name of the Bank Account (e.g. 'Checking Account - Acme')",
        },
        "company": {
            "type": "string",
            "description": "Company name (defaults to active user company)",
        },
        "transaction_type": {
            "type": "string",
            "enum": ["All", "Deposit", "Withdrawal"],
            "description": "Filter by deposit (inflow) or withdrawal (outflow). Default: 'All'",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of transactions to return (default: 20, max: 50)",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Bank Transaction"
    required_ptype = "read"

    def execute(
        self,
        bank_account: Optional[str] = None,
        company: Optional[str] = None,
        transaction_type: str = "All",
        limit: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        company = company or self.company or frappe.defaults.get_user_default("company", self.user)
        limit = min(int(limit or 20), 50)

        frappe.has_permission("Bank Transaction", ptype="read", throw=True)

        filters = [
            ["docstatus", "=", 1],
            ["unallocated_amount", ">", 0],
        ]

        if company:
            filters.append(["company", "=", company])
        if bank_account:
            filters.append(["bank_account", "=", bank_account])

        if transaction_type == "Deposit":
            filters.append(["deposit", ">", 0])
        elif transaction_type == "Withdrawal":
            filters.append(["withdrawal", ">", 0])

        transactions = frappe.get_all(
            "Bank Transaction",
            filters=filters,
            fields=[
                "name",
                "date",
                "bank_account",
                "deposit",
                "withdrawal",
                "currency",
                "unallocated_amount",
                "allocated_amount",
                "reference_number",
                "party_type",
                "party",
                "description",
            ],
            order_by="date desc, creation desc",
            limit_page_length=limit,
        )

        return {
            "count": len(transactions),
            "bank_account": bank_account or "All Accounts",
            "company": company,
            "transactions": transactions,
        }
