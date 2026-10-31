import json
import uuid
from typing import Any, Dict, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime


class HITLGuard:
    """Human-in-the-Loop (HITL) Guard.

    Enforces mandatory human confirmation for high-risk actions (document
    submissions, cancellations, deletions, and direct financial ledger entries).
    """

    # Tools that always require human approval unless explicitly auto-approved
    ALWAYS_REQUIRE_APPROVAL_TOOLS = {
        "core.submit_document",
        "accounting.create_journal_entry",
        "accounting.create_payment_entry",
        "banking.reconcile_voucher",
        "banking.auto_reconcile",
    }

    # Action types that inherently mutate financial or legal records
    CRITICAL_ACTION_TYPES = {"Submit", "Cancel", "Delete"}

    def __init__(self, user: str, session_id: Optional[str] = None, company: Optional[str] = None):
        self.user = user
        self.session_id = session_id
        self.company = company

    def requires_approval(
        self, tool_name: str, tool_input: Dict[str, Any], action_type: str = "Read"
    ) -> Tuple[bool, str, str]:
        """Determine if a tool call requires explicit human approval.

        Returns:
            (needs_approval: bool, action_type: str, human_readable_summary: str)
        """
        # Read operations and reports never require confirmation
        if action_type in ("Read", "Report") and tool_name not in self.ALWAYS_REQUIRE_APPROVAL_TOOLS:
            return False, action_type, ""

        # Check settings
        settings = None
        try:
            settings = frappe.get_cached_doc("AI Bot Settings")
        except Exception:
            pass

        # If HITL is globally disabled by admin, allow execution
        if settings and hasattr(settings, "require_human_approval") and not settings.require_human_approval:
            return False, action_type, ""

        auto_approve_drafts = True
        if settings and hasattr(settings, "hitl_auto_approve_drafts"):
            auto_approve_drafts = bool(settings.hitl_auto_approve_drafts)

        # Check critical triggers
        is_critical = (
            action_type in self.CRITICAL_ACTION_TYPES
            or tool_name in self.ALWAYS_REQUIRE_APPROVAL_TOOLS
        )

        if not is_critical:
            # If it's a draft create/update, check if auto-approval of drafts is allowed
            if auto_approve_drafts:
                return False, action_type, ""

        # Build human-readable summary
        summary = self._generate_summary(tool_name, tool_input, action_type)
        return True, action_type, summary

    def _generate_summary(self, tool_name: str, tool_input: Dict[str, Any], action_type: str) -> str:
        """Generate a concise, user-friendly summary of the pending action."""
        doctype = tool_input.get("doctype", "")
        doc_name = tool_input.get("name", "")

        if tool_name == "core.submit_document":
            return f"Submit {doctype} '{doc_name}'"

        if tool_name == "core.create_document":
            return f"Create new {doctype} document"

        if tool_name == "core.update_document":
            return f"Update {doctype} '{doc_name}'"

        if tool_name == "accounting.create_journal_entry":
            v_type = tool_input.get("voucher_type", "Journal Entry")
            return f"Create & post {v_type}"

        if tool_name == "accounting.create_payment_entry":
            party = tool_input.get("party", "")
            amount = tool_input.get("paid_amount", "")
            return f"Create & post Payment Entry of {amount} for {party}".strip()

        if tool_name == "stock.create_stock_entry":
            purpose = tool_input.get("purpose", "Stock Entry")
            return f"Create Stock Entry ({purpose})"

        if tool_name == "banking.reconcile_voucher":
            bt_name = tool_input.get("bank_transaction", "")
            vouchers = tool_input.get("vouchers", [])
            return f"Reconcile Bank Transaction '{bt_name}' with {len(vouchers)} voucher(s)"

        if tool_name == "banking.auto_reconcile":
            ba = tool_input.get("bank_account", "")
            return f"Run batch auto-reconciliation for '{ba}'"

        return f"{action_type} via {tool_name}"

    def stage_pending_action(
        self, tool_name: str, tool_input: Dict[str, Any], action_type: str, summary: str
    ) -> Dict[str, Any]:
        """Stage an action in the AI Pending Action doctype and prepare response."""
        action_id = f"ACT-{uuid.uuid4().hex[:12].upper()}"
        expires_at = add_to_date(now_datetime(), hours=1)

        doc = frappe.get_doc({
            "doctype": "AI Pending Action",
            "action_id": action_id,
            "status": "Pending",
            "action_type": action_type,
            "tool_name": tool_name,
            "summary": summary,
            "session": self.session_id,
            "user": self.user,
            "company": self.company,
            "expires_at": expires_at,
            "tool_input_json": json.dumps(tool_input, default=str),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "pending_approval",
            "action_id": action_id,
            "action_name": doc.name,
            "action_type": action_type,
            "summary": summary,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "message": (
                f"ACTION PENDING HUMAN AUTHORIZATION: '{summary}'. "
                "A confirmation card with [Approve & Execute] and [Reject] buttons has been sent to the user in Desk. "
                "Inform the user clearly of the action and ask them to review and approve it."
            ),
        }


def execute_action(action_id: str, user: str) -> Dict[str, Any]:
    """Execute a previously staged pending action after user authorization."""
    from erpnext_ai_bots.guards.permissions import PermissionGuard
    from erpnext_ai_bots.tools.registry import ToolRegistry

    # Find pending action
    action = frappe.db.get_value(
        "AI Pending Action",
        {"action_id": action_id},
        ["name", "status", "user", "company", "tool_name", "tool_input_json", "expires_at", "summary"],
        as_dict=True,
    )
    if not action:
        # Fallback to name search
        action = frappe.db.get_value(
            "AI Pending Action",
            action_id,
            ["name", "status", "user", "company", "tool_name", "tool_input_json", "expires_at", "summary"],
            as_dict=True,
        )

    if not action:
        frappe.throw(_("Pending action '{0}' not found").format(action_id), frappe.DoesNotExistError)

    if action.status != "Pending":
        frappe.throw(_("Action has already been {0}").format(action.status.lower()))

    # Verify authorization (action owner or System Manager)
    user_roles = set(frappe.get_roles(user))
    if action.user != user and "System Manager" not in user_roles and user != "Administrator":
        frappe.throw(_("You are not authorized to approve this action"), frappe.PermissionError)

    # Check expiration
    if action.expires_at and str(now_datetime()) > str(action.expires_at):
        frappe.db.set_value("AI Pending Action", action.name, "status", "Expired")
        frappe.db.commit()
        frappe.throw(_("This action approval request has expired. Please request the action again."))

    tool_input = json.loads(action.tool_input_json or "{}")

    # Re-verify permissions at execution time
    guard = PermissionGuard(user=user)
    guard.check(action.tool_name, tool_input)

    # Execute tool
    registry = ToolRegistry(user=user, company=action.company)
    tool_fn = registry.get_tool(action.tool_name)
    result = tool_fn.execute(**tool_input)

    # Update action state
    frappe.db.set_value(
        "AI Pending Action",
        action.name,
        {
            "status": "Approved",
            "executed_at": now_datetime(),
            "executed_by": user,
            "result_json": json.dumps(result, default=str),
        },
    )

    # Record in audit log
    try:
        frappe.get_doc({
            "doctype": "AI Audit Log",
            "user": user,
            "company": action.company,
            "tool_name": action.tool_name,
            "tool_input_json": action.tool_input_json,
            "tool_output_json": json.dumps(result, default=str),
            "tool_result_status": "Success",
            "action_type": "ApprovedByHuman",
        }).insert(ignore_permissions=True)
    except Exception:
        pass

    frappe.db.commit()

    # Notify via realtime event
    frappe.publish_realtime(
        event="ai_action_resolved",
        message={
            "action_id": action_id,
            "status": "Approved",
            "summary": action.summary,
            "result": result,
        },
        user=user,
        after_commit=False,
    )

    return {"status": "success", "action_id": action_id, "result": result}


def reject_action(action_id: str, user: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Reject a staged pending action."""
    action = frappe.db.get_value(
        "AI Pending Action",
        {"action_id": action_id},
        ["name", "status", "user", "company", "summary"],
        as_dict=True,
    )
    if not action:
        action = frappe.db.get_value(
            "AI Pending Action",
            action_id,
            ["name", "status", "user", "company", "summary"],
            as_dict=True,
        )

    if not action:
        frappe.throw(_("Pending action '{0}' not found").format(action_id), frappe.DoesNotExistError)

    if action.status != "Pending":
        frappe.throw(_("Action has already been {0}").format(action.status.lower()))

    user_roles = set(frappe.get_roles(user))
    if action.user != user and "System Manager" not in user_roles and user != "Administrator":
        frappe.throw(_("You are not authorized to reject this action"), frappe.PermissionError)

    frappe.db.set_value(
        "AI Pending Action",
        action.name,
        {
            "status": "Rejected",
            "rejection_reason": reason or "Rejected by user in Desk",
        },
    )

    try:
        frappe.get_doc({
            "doctype": "AI Audit Log",
            "user": user,
            "company": action.company,
            "tool_name": "ai.reject_action",
            "tool_input_json": json.dumps({"action_id": action_id, "reason": reason}),
            "tool_output_json": json.dumps({"status": "rejected"}),
            "tool_result_status": "Success",
            "action_type": "RejectedByHuman",
        }).insert(ignore_permissions=True)
    except Exception:
        pass

    frappe.db.commit()

    frappe.publish_realtime(
        event="ai_action_resolved",
        message={
            "action_id": action_id,
            "status": "Rejected",
            "summary": action.summary,
            "reason": reason,
        },
        user=user,
        after_commit=False,
    )

    return {"status": "rejected", "action_id": action_id}

