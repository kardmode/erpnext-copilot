# Copyright (c) 2026, Benchi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIPendingAction(Document):
    pass


def has_permission(doc, ptype, user):
    """Only the session user or System Manager can view or act on a pending action."""
    if doc.user == user:
        return True
    if "System Manager" in frappe.get_roles(user):
        return True
    return False

