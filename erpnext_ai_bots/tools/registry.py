import frappe
from importlib import import_module
from typing import Dict, List

# Canonical tool map: namespace.tool_name -> module.ClassName
TOOL_MAP = {
    # Core tools
    "core.get_document": "erpnext_ai_bots.tools.core.get_document.GetDocumentTool",
    "core.get_list": "erpnext_ai_bots.tools.core.get_list.GetListTool",
    "core.create_document": "erpnext_ai_bots.tools.core.create_document.CreateDocumentTool",
    "core.update_document": "erpnext_ai_bots.tools.core.update_document.UpdateDocumentTool",
    "core.submit_document": "erpnext_ai_bots.tools.core.submit_document.SubmitDocumentTool",
    "core.run_report": "erpnext_ai_bots.tools.core.run_report.RunReportTool",
    "core.raw_sql": "erpnext_ai_bots.tools.core.raw_sql.RawSQLTool",
    "core.frappe_api": "erpnext_ai_bots.tools.core.frappe_api.FrappeAPITool",
    "core.send_email": "erpnext_ai_bots.tools.core.send_email.SendEmailTool",
    "core.send_report_email": "erpnext_ai_bots.tools.core.send_report_email.SendReportEmailTool",
    "core.analyze_image": "erpnext_ai_bots.tools.core.analyze_image.AnalyzeImageTool",
    "core.read_file": "erpnext_ai_bots.tools.core.read_file.ReadFileTool",

    # Accounting tools
    "accounting.get_trial_balance": "erpnext_ai_bots.tools.accounting.trial_balance.GetTrialBalanceTool",
    "accounting.get_outstanding_invoices": "erpnext_ai_bots.tools.accounting.outstanding_invoices.GetOutstandingInvoicesTool",
    "accounting.get_bank_balances": "erpnext_ai_bots.tools.accounting.bank_balances.GetBankBalancesTool",
    "accounting.get_profit_and_loss": "erpnext_ai_bots.tools.accounting.profit_and_loss.GetProfitAndLossTool",
    "accounting.create_journal_entry": "erpnext_ai_bots.tools.accounting.journal_entry.CreateJournalEntryTool",
    "accounting.get_account_balance": "erpnext_ai_bots.tools.accounting.account_balance.GetAccountBalanceTool",
    "accounting.get_gross_margin": "erpnext_ai_bots.tools.accounting.gross_margin.GetGrossMarginTool",

    # HR tools
    "hr.get_leave_balance": "erpnext_ai_bots.tools.hr.leave_balance.GetLeaveBalanceTool",
    "hr.create_leave_application": "erpnext_ai_bots.tools.hr.leave_application.CreateLeaveApplicationTool",
    "hr.get_salary_slip": "erpnext_ai_bots.tools.hr.salary_slip.GetSalarySlipTool",
    "hr.get_attendance_summary": "erpnext_ai_bots.tools.hr.attendance.GetAttendanceSummaryTool",
    "hr.get_employee_info": "erpnext_ai_bots.tools.hr.employee_info.GetEmployeeInfoTool",

    # Stock tools
    "stock.get_stock_balance": "erpnext_ai_bots.tools.stock.stock_balance.GetStockBalanceTool",
    "stock.create_stock_entry": "erpnext_ai_bots.tools.stock.stock_entry.CreateStockEntryTool",
    "stock.get_warehouse_summary": "erpnext_ai_bots.tools.stock.warehouse_summary.GetWarehouseSummaryTool",
    "stock.get_item_info": "erpnext_ai_bots.tools.stock.item_info.GetItemInfoTool",
    "stock.get_reorder_levels": "erpnext_ai_bots.tools.stock.reorder.GetReorderLevelsTool",
    "stock.create_item": "erpnext_ai_bots.tools.stock.create_item.CreateItemTool",
    "stock.get_inventory_days": "erpnext_ai_bots.tools.stock.inventory_days.GetInventoryDaysTool",
    "stock.get_stock_turnover": "erpnext_ai_bots.tools.stock.stock_turnover.GetStockTurnoverTool",

    # Sales tools
    "sales.get_pipeline": "erpnext_ai_bots.tools.sales.pipeline.GetPipelineTool",
    "sales.create_quotation": "erpnext_ai_bots.tools.sales.quotation.CreateQuotationTool",
    "sales.get_sales_orders": "erpnext_ai_bots.tools.sales.sales_order.GetSalesOrdersTool",
    "sales.get_customer_info": "erpnext_ai_bots.tools.sales.customer_info.GetCustomerInfoTool",
    "sales.get_revenue_summary": "erpnext_ai_bots.tools.sales.revenue_summary.GetRevenueSummaryTool",
    "sales.create_customer": "erpnext_ai_bots.tools.sales.create_customer.CreateCustomerTool",
    "sales.get_branch_performance": "erpnext_ai_bots.tools.sales.branch_performance.GetBranchPerformanceTool",
    "sales.get_sales_dashboard": "erpnext_ai_bots.tools.sales.sales_dashboard.GetSalesDashboardTool",

    # Meta tools
    "meta.spawn_subagent": "erpnext_ai_bots.tools.meta.spawn_subagent.SpawnSubagentTool",
    "meta.schedule_task": "erpnext_ai_bots.tools.meta.schedule_task.ScheduleTaskTool",
    "meta.saved_report": "erpnext_ai_bots.tools.meta.saved_report.SavedReportTool",

    # Accounting (extended)
    "accounting.create_payment_entry": "erpnext_ai_bots.tools.accounting.payment_entry.CreatePaymentEntryTool",
    "accounting.get_general_ledger": "erpnext_ai_bots.tools.accounting.general_ledger.GetGeneralLedgerTool",

    # Purchase tools
    "purchase.create_purchase_order": "erpnext_ai_bots.tools.purchase.purchase_order.CreatePurchaseOrderTool",
    "purchase.get_supplier_info": "erpnext_ai_bots.tools.purchase.supplier_info.GetSupplierInfoTool",
    "purchase.get_purchase_invoices": "erpnext_ai_bots.tools.purchase.purchase_invoice.GetPurchaseInvoicesTool",
    "purchase.create_supplier": "erpnext_ai_bots.tools.purchase.create_supplier.CreateSupplierTool",

    # CRM tools
    "crm.manage_lead": "erpnext_ai_bots.tools.crm.lead.LeadTool",
    "crm.manage_opportunity": "erpnext_ai_bots.tools.crm.opportunity.OpportunityTool",

    # Project tools
    "project.manage_project": "erpnext_ai_bots.tools.project.project.ProjectTool",
    "project.manage_task": "erpnext_ai_bots.tools.project.task.TaskTool",

    # Support tools
    "support.manage_issue": "erpnext_ai_bots.tools.support.issue.IssueTool",

    # Asset tools
    "asset.manage_asset": "erpnext_ai_bots.tools.asset.asset.AssetTool",

    # Banking & Reconciliation tools
    "banking.get_unreconciled_transactions": "erpnext_ai_bots.tools.banking.unreconciled_transactions.GetUnreconciledTransactionsTool",
    "banking.suggest_matches": "erpnext_ai_bots.tools.banking.suggest_matches.SuggestMatchesTool",
    "banking.reconcile_voucher": "erpnext_ai_bots.tools.banking.reconcile_voucher.ReconcileVoucherTool",
    "banking.auto_reconcile": "erpnext_ai_bots.tools.banking.auto_reconcile.AutoReconcileTool",
}


from typing import Dict, List, Optional, Set

# Universal core tools always included regardless of conversation category
CORE_TOOLS: Set[str] = {
    "core.get_document",
    "core.get_list",
    "core.create_document",
    "core.update_document",
    "core.submit_document",
    "core.run_report",
    "core.raw_sql",
    "core.frappe_api",
    "core.send_email",
    "core.send_report_email",
    "core.analyze_image",
    "core.read_file",
    "meta.spawn_subagent",
    "meta.schedule_task",
    "meta.saved_report",
}

# Domain-specific category tool mappings
CATEGORY_TOOL_MAP: Dict[str, Set[str]] = {
    "Finance": {
        "accounting.get_trial_balance",
        "accounting.get_outstanding_invoices",
        "accounting.get_bank_balances",
        "accounting.get_profit_and_loss",
        "accounting.create_journal_entry",
        "accounting.get_account_balance",
        "accounting.get_gross_margin",
        "accounting.create_payment_entry",
        "accounting.get_general_ledger",
        "purchase.get_purchase_invoices",
        "banking.get_unreconciled_transactions",
        "banking.suggest_matches",
        "banking.reconcile_voucher",
        "banking.auto_reconcile",
    },
    "Banking": {
        "accounting.get_bank_balances",
        "accounting.create_payment_entry",
        "accounting.create_journal_entry",
        "banking.get_unreconciled_transactions",
        "banking.suggest_matches",
        "banking.reconcile_voucher",
        "banking.auto_reconcile",
    },
    "Sales": {
        "sales.get_pipeline",
        "sales.create_quotation",
        "sales.get_sales_orders",
        "sales.get_customer_info",
        "sales.get_revenue_summary",
        "sales.create_customer",
        "sales.get_branch_performance",
        "sales.get_sales_dashboard",
        "crm.manage_lead",
        "crm.manage_opportunity",
    },
    "Stock": {
        "stock.get_stock_balance",
        "stock.create_stock_entry",
        "stock.get_warehouse_summary",
        "stock.get_item_info",
        "stock.get_reorder_levels",
        "stock.create_item",
        "stock.get_inventory_days",
        "stock.get_stock_turnover",
        "purchase.create_purchase_order",
        "purchase.get_supplier_info",
    },
    "HR": {
        "hr.get_leave_balance",
        "hr.create_leave_application",
        "hr.get_salary_slip",
        "hr.get_attendance_summary",
        "hr.get_employee_info",
    },
    "Purchase": {
        "purchase.create_purchase_order",
        "purchase.get_supplier_info",
        "purchase.get_purchase_invoices",
        "purchase.create_supplier",
    },
    "Projects": {
        "project.manage_project",
        "project.manage_task",
        "support.manage_issue",
        "asset.manage_asset",
    },
}

# Domain keywords for dynamic message text intent detection
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Finance": [
        "invoice", "payment", "journal", "bank", "balance",
        "p&l", "profit", "loss", "ledger", "account", "tax",
        "receivable", "payable", "expense", "budget", "supplier",
        "purchase", "overdue", "outstanding", "credit", "debit",
        "revenue", "cost", "financial", "fiscal",
    ],
    "Sales": [
        "quotation", "customer", "order", "pipeline", "quote",
        "lead", "opportunity", "crm", "sale", "deal", "prospect",
        "contract", "discount", "pricing", "client",
    ],
    "Stock": [
        "stock", "item", "warehouse", "inventory", "reorder",
        "material", "bin", "transfer", "receipt", "delivery",
        "batch", "serial", "product", "goods",
    ],
    "HR": [
        "leave", "salary", "employee", "attendance", "hr",
        "payroll", "appraisal", "recruitment", "department",
        "overtime", "holiday", "staff", "worker",
    ],
    "Purchase": [
        "supplier", "purchase order", "po", "vendor", "procurement",
    ],
    "Projects": [
        "project", "task", "milestone", "timesheet", "issue",
        "ticket", "support", "asset",
    ],
    "Banking": [
        "reconcile", "reconciliation", "bank statement", "unreconciled",
        "clearance", "unallocated", "bank transaction", "bank feed",
        "statement", "deposit", "withdrawal",
    ],
}


class ToolRegistry:
    """Manages tool loading, namespacing, and schema generation.
    Tools are loaded lazily and cached per-request.
    """

    def __init__(self, user: str, company: str):
        self.user = user
        self.company = company
        self._cache: Dict[str, object] = {}

    def get_tool(self, namespaced_name: str):
        """Get a tool instance by its namespaced name."""
        if namespaced_name not in self._cache:
            class_path = TOOL_MAP.get(namespaced_name)
            if not class_path:
                raise ValueError(f"Unknown tool: {namespaced_name}")

            module_path, class_name = class_path.rsplit(".", 1)
            module = import_module(module_path)
            tool_class = getattr(module, class_name)
            self._cache[namespaced_name] = tool_class(
                user=self.user, company=self.company
            )

        return self._cache[namespaced_name]

    def resolve_active_tools(
        self, category: Optional[str] = None, message_text: Optional[str] = None
    ) -> List[str]:
        """Dynamically resolve relevant tools for the current context.

        1. Starts with core CRUD and communication tools.
        2. Detects context category from parameter or message keywords.
        3. Adds category-specific tools.
        4. Filters out tools blocked by user role or Frappe permissions.
        """
        active_tools = set(CORE_TOOLS)

        matched_categories = set()
        if category and category in CATEGORY_TOOL_MAP:
            matched_categories.add(category)

        if message_text:
            msg_lower = str(message_text).lower()
            for cat, kw_list in CATEGORY_KEYWORDS.items():
                if any(kw in msg_lower for kw in kw_list):
                    matched_categories.add(cat)

        if matched_categories:
            for cat in matched_categories:
                active_tools.update(CATEGORY_TOOL_MAP.get(cat, set()))
        else:
            # Fallback when ambiguous or general: include all tools from TOOL_MAP
            active_tools.update(TOOL_MAP.keys())

        # Role-based filtering
        user_roles = set()
        try:
            if self.user and self.user != "Administrator":
                user_roles = set(frappe.get_roles(self.user))
        except Exception:
            pass

        # Exclude raw_sql for non-System Manager
        if self.user != "Administrator" and "System Manager" not in user_roles:
            active_tools.discard("core.raw_sql")

        # Exclude management-only tools for non-managers
        management_roles = {"System Manager", "Accounts Manager", "Sales Manager", "Stock Manager"}
        has_mgmt_role = bool(self.user == "Administrator" or user_roles.intersection(management_roles))
        if not has_mgmt_role:
            mgmt_only_tools = {
                "accounting.get_gross_margin",
                "sales.get_branch_performance",
                "sales.get_sales_dashboard",
                "stock.get_inventory_days",
                "stock.get_stock_turnover",
                "accounting.get_profit_and_loss",
                "accounting.get_trial_balance",
                "accounting.get_general_ledger",
            }
            active_tools.difference_update(mgmt_only_tools)

        return sorted([t for t in active_tools if t in TOOL_MAP])

    def get_all_schemas(
        self, category: Optional[str] = None, message_text: Optional[str] = None
    ) -> list:
        """Return tool schemas in Anthropic format for dynamically scoped tools."""
        tool_names = self.resolve_active_tools(category=category, message_text=message_text)
        schemas = []
        for namespaced_name in tool_names:
            try:
                tool = self.get_tool(namespaced_name)
                schemas.append(tool.schema())
            except Exception as e:
                import frappe
                frappe.log_error(
                    title=f"Tool load failed: {namespaced_name}",
                    message=str(e),
                )
        return schemas

    def get_openai_schemas(
        self, category: Optional[str] = None, message_text: Optional[str] = None
    ) -> list:
        """Return tool schemas in OpenAI Responses API format for dynamically scoped tools."""
        tool_names = self.resolve_active_tools(category=category, message_text=message_text)
        schemas = []
        for namespaced_name in tool_names:
            try:
                tool = self.get_tool(namespaced_name)
                anthropic_schema = tool.schema()
            except Exception as e:
                import frappe
                frappe.log_error(
                    title=f"Tool load failed: {namespaced_name}",
                    message=str(e),
                )
                continue
            safe_name = anthropic_schema["name"].replace(".", "_")
            openai_schema = {
                "type": "function",
                "name": safe_name,
                "description": anthropic_schema["description"],
                "parameters": anthropic_schema["input_schema"],
            }
            schemas.append(openai_schema)
        return schemas

    def get_tool_by_openai_name(self, openai_name: str):
        """Look up a tool by its OpenAI-safe name (underscores instead of dots)."""
        # Convert back: core_get_list -> core.get_list
        dotted_name = openai_name.replace("_", ".", 1)
        if dotted_name in TOOL_MAP:
            return self.get_tool(dotted_name)
        # Fallback: try direct match
        if openai_name in TOOL_MAP:
            return self.get_tool(openai_name)
        raise ValueError(f"Unknown tool: {openai_name}")

    def resolve_tool_subset(self, patterns: list) -> list:
        """Resolve glob-like patterns to tool instances.
        E.g. ["accounting.*", "core.get_document"] -> list of tool instances
        """
        tools = []
        for pattern in patterns:
            if pattern.endswith(".*"):
                namespace = pattern[:-2]
                for name in TOOL_MAP:
                    if name.startswith(namespace + "."):
                        tools.append(self.get_tool(name))
            elif pattern in TOOL_MAP:
                tools.append(self.get_tool(pattern))
        return tools
