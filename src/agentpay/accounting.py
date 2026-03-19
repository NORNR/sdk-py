from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Protocol

from .client import AgentPayClient, Wallet
from .money import AmountLike, usd_decimal, usd_float


class _ClientLike(Protocol):
    def get_monthly_statement(self, month: str | None = None) -> Any: ...
    def get_audit_review(self, fmt: str = "json") -> Any: ...
    def get_cost_report(self, fmt: str = "json") -> Any: ...
    def list_webhook_deliveries(self) -> Any: ...


def _coerce_client(source: AgentPayClient | Wallet | _ClientLike) -> _ClientLike:
    if isinstance(source, Wallet):
        return source.client
    return source


def _month_token(month: str | None = None) -> str:
    return month or date.today().strftime("%Y-%m")


def _money(payload: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        if payload.get(key) is not None:
            return usd_decimal(payload.get(key))
    return usd_decimal(0)


@dataclass(frozen=True)
class AccountingLine:
    account_code: str
    direction: str
    amount_usd: Decimal
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountingEntry:
    reference: str
    entry_date: str
    memo: str
    debit_lines: list[AccountingLine]
    credit_lines: list[AccountingLine]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountingBatch:
    workspace_label: str
    month: str
    entries: list[AccountingEntry]
    source_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspaceLabel": self.workspace_label,
            "month": self.month,
            "entryCount": len(self.entries),
            "sourceSummary": self.source_summary,
            "entries": [
                {
                    "reference": entry.reference,
                    "entryDate": entry.entry_date,
                    "memo": entry.memo,
                    "metadata": entry.metadata,
                    "debitLines": [
                        {**line.__dict__, "amount_usd": usd_float(line.amount_usd)}
                        for line in entry.debit_lines
                    ],
                    "creditLines": [
                        {**line.__dict__, "amount_usd": usd_float(line.amount_usd)}
                        for line in entry.credit_lines
                    ],
                }
                for entry in self.entries
            ],
        }

    def to_quickbooks_payload(self) -> dict[str, Any]:
        return {
            "JournalEntries": [
                {
                    "DocNumber": entry.reference,
                    "TxnDate": entry.entry_date,
                    "PrivateNote": entry.memo,
                    "Line": [
                        *[
                            {
                                "Description": line.description,
                                "Amount": usd_float(line.amount_usd),
                                "DetailType": "JournalEntryLineDetail",
                                "JournalEntryLineDetail": {"PostingType": "Debit", "AccountRef": {"value": line.account_code}},
                            }
                            for line in entry.debit_lines
                        ],
                        *[
                            {
                                "Description": line.description,
                                "Amount": usd_float(line.amount_usd),
                                "DetailType": "JournalEntryLineDetail",
                                "JournalEntryLineDetail": {"PostingType": "Credit", "AccountRef": {"value": line.account_code}},
                            }
                            for line in entry.credit_lines
                        ],
                    ],
                }
                for entry in self.entries
            ]
        }

    def to_xero_payload(self) -> dict[str, Any]:
        return {
            "ManualJournals": [
                {
                    "Narration": entry.memo,
                    "Date": entry.entry_date,
                    "Reference": entry.reference,
                    "JournalLines": [
                        *[
                            {
                                "AccountCode": line.account_code,
                                "Description": line.description,
                                "LineAmount": usd_float(line.amount_usd),
                                "IsDebit": True,
                            }
                            for line in entry.debit_lines
                        ],
                        *[
                            {
                                "AccountCode": line.account_code,
                                "Description": line.description,
                                "LineAmount": usd_float(line.amount_usd),
                                "IsDebit": False,
                            }
                            for line in entry.credit_lines
                        ],
                    ],
                }
                for entry in self.entries
            ]
        }

    def to_fortnox_payload(self) -> dict[str, Any]:
        return {
            "Vouchers": [
                {
                    "Description": entry.memo,
                    "VoucherDate": entry.entry_date,
                    "ReferenceType": "NORNR",
                    "ReferenceNumber": entry.reference,
                    "VoucherRows": [
                        *[
                            {
                                "Account": int(line.account_code),
                                "Debit": usd_float(line.amount_usd),
                                "Credit": 0,
                                "Description": line.description,
                            }
                            for line in entry.debit_lines
                        ],
                        *[
                            {
                                "Account": int(line.account_code),
                                "Debit": 0,
                                "Credit": usd_float(line.amount_usd),
                                "Description": line.description,
                            }
                            for line in entry.credit_lines
                        ],
                    ],
                }
                for entry in self.entries
            ]
        }

    def for_provider(self, provider: str) -> dict[str, Any]:
        normalized = provider.strip().lower()
        if normalized == "quickbooks":
            return self.to_quickbooks_payload()
        if normalized == "xero":
            return self.to_xero_payload()
        if normalized == "fortnox":
            return self.to_fortnox_payload()
        raise ValueError(f"Unsupported accounting provider: {provider}")


@dataclass(frozen=True)
class AccountingDelivery:
    delivery_id: str
    event_type: str
    status: str
    created_at: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class AccountingWorkerResult:
    provider: str
    batch: AccountingBatch
    exported_payload: dict[str, Any]
    matched_deliveries: list[AccountingDelivery]


def _statement_lines(statement: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("entries", "transactions", "ledgerEntries", "lines", "items"):
        value = statement.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _summary_entry(month: str, review: Mapping[str, Any], costs: Mapping[str, Any]) -> AccountingEntry:
    executive = dict(review.get("executiveSummary") or {})
    finance = dict(review.get("financeActivity") or {})
    total_spend = _money(costs, "totalSpendUsd", "spendUsd", "amountUsd") or _money(finance, "totalSpendUsd", "spendUsd")
    fees = _money(finance, "feesUsd", "totalFeesUsd")
    memo = executive.get("headline") or "NORNR governed spend summary"
    debits = [
        AccountingLine("6100", "debit", total_spend, "Governed agent spend"),
    ]
    credits = [
        AccountingLine("1930", "credit", total_spend, "Cash / treasury outflow"),
    ]
    if fees:
        debits.append(AccountingLine("6570", "debit", fees, "NORNR / rail fees"))
        credits.append(AccountingLine("1930", "credit", fees, "Cash / treasury outflow"))
    return AccountingEntry(
        reference=f"NORNR-{month}-SUMMARY",
        entry_date=f"{month}-01",
        memo=memo,
        debit_lines=debits,
        credit_lines=credits,
        metadata={"source": "summary"},
    )


def _entry_from_statement_line(month: str, line: Mapping[str, Any], index: int) -> AccountingEntry:
    amount = abs(_money(line, "amountUsd", "totalUsd", "netUsd", "amount"))
    counterparty = str(line.get("counterparty") or line.get("destination") or "external")
    status = str(line.get("status") or line.get("type") or "posted")
    entry_date = str(line.get("createdAt") or line.get("recordedAt") or f"{month}-01")[:10]
    memo = str(line.get("purpose") or f"NORNR governed spend to {counterparty}")
    debit_code = "6100" if status not in {"fee", "fees"} else "6570"
    debit_line = AccountingLine(debit_code, "debit", amount, memo, metadata={"counterparty": counterparty, "status": status})
    credit_line = AccountingLine("1930", "credit", amount, f"Treasury outflow for {counterparty}", metadata={"status": status})
    return AccountingEntry(
        reference=str(line.get("id") or line.get("paymentIntentId") or f"NORNR-{month}-{index:03d}"),
        entry_date=entry_date,
        memo=memo,
        debit_lines=[debit_line],
        credit_lines=[credit_line],
        metadata=dict(line),
    )


class AccountingBridge:
    """Convert NORNR audit and statement data into accounting-friendly payloads."""

    def __init__(self, source: AgentPayClient | Wallet | _ClientLike, *, workspace_label: str | None = None) -> None:
        self.client = _coerce_client(source)
        self.workspace_label = workspace_label or "NORNR workspace"

    def fetch_source(self, *, month: str | None = None) -> dict[str, Any]:
        return {
            "month": _month_token(month),
            "monthlyStatement": self.client.get_monthly_statement(month),
            "auditReview": self.client.get_audit_review(),
            "costReport": self.client.get_cost_report(),
        }

    def build_batch(self, *, month: str | None = None) -> AccountingBatch:
        source = self.fetch_source(month=month)
        resolved_month = source["month"]
        statement = dict(source.get("monthlyStatement") or {})
        review = dict(source.get("auditReview") or {})
        costs = dict(source.get("costReport") or {})
        entries = [_entry_from_statement_line(resolved_month, line, index + 1) for index, line in enumerate(_statement_lines(statement))]
        if not entries:
            entries = [_summary_entry(resolved_month, review, costs)]
        source_summary = {
            "statementMonth": resolved_month,
            "statementLines": len(_statement_lines(statement)),
            "costReportHeadline": costs.get("headline"),
            "financePacketScore": ((review.get("financePacket") or {}).get("score") if isinstance(review.get("financePacket"), Mapping) else None),
        }
        return AccountingBatch(
            workspace_label=self.workspace_label,
            month=resolved_month,
            entries=entries,
            source_summary=source_summary,
        )

    def export_for_provider(self, provider: str, *, month: str | None = None) -> dict[str, Any]:
        return self.build_batch(month=month).for_provider(provider)


class AccountingWorker:
    """Webhook-aware accounting exporter for finance bridges."""

    def __init__(self, source: AgentPayClient | Wallet | _ClientLike, *, workspace_label: str | None = None) -> None:
        self.client = _coerce_client(source)
        self.bridge = AccountingBridge(source, workspace_label=workspace_label)

    def matching_deliveries(self, *, event_types: tuple[str, ...] = ("payment.intent.created", "receipt.created", "statement.monthly.ready")) -> list[AccountingDelivery]:
        deliveries = self.client.list_webhook_deliveries() or {}
        items: Any
        if isinstance(deliveries, list):
            items = deliveries
        elif isinstance(deliveries, Mapping):
            items = deliveries.get("items") or deliveries.get("deliveries") or deliveries
        else:
            return []
        if not isinstance(items, list):
            return []
        matches: list[AccountingDelivery] = []
        for item in items:
            payload = item.to_dict() if hasattr(item, "to_dict") else item
            if not isinstance(payload, Mapping):
                continue
            event_type = str(payload.get("eventType") or payload.get("type") or "")
            if event_types and event_type not in event_types:
                continue
            matches.append(
                AccountingDelivery(
                    delivery_id=str(payload.get("id") or payload.get("deliveryId") or ""),
                    event_type=event_type,
                    status=str(payload.get("status") or "unknown"),
                    created_at=payload.get("createdAt"),
                    payload=dict(payload.get("payload") or {}),
                )
            )
        return matches

    def export(
        self,
        *,
        provider: str,
        month: str | None = None,
        event_types: tuple[str, ...] = ("payment.intent.created", "receipt.created", "statement.monthly.ready"),
    ) -> AccountingWorkerResult:
        batch = self.bridge.build_batch(month=month)
        return AccountingWorkerResult(
            provider=provider,
            batch=batch,
            exported_payload=batch.for_provider(provider),
            matched_deliveries=self.matching_deliveries(event_types=event_types),
        )


def build_accounting_batch(
    source: AgentPayClient | Wallet | _ClientLike,
    *,
    month: str | None = None,
    workspace_label: str | None = None,
) -> AccountingBatch:
    """Build a portable accounting batch from NORNR statement and audit data."""

    return AccountingBridge(source, workspace_label=workspace_label).build_batch(month=month)


def export_accounting_provider_payload(
    source: AgentPayClient | Wallet | _ClientLike,
    *,
    provider: str,
    month: str | None = None,
    workspace_label: str | None = None,
) -> dict[str, Any]:
    """Build a provider-specific accounting payload directly from NORNR data."""

    return AccountingBridge(source, workspace_label=workspace_label).export_for_provider(provider, month=month)
