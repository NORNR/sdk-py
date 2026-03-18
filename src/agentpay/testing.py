from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AuditReviewRecord, BalanceRecord, DecisionRecord


def mock_decision(status: str = "approved", *, approval_id: str = "approval_mock") -> DecisionRecord:
    payload = {
        "paymentIntent": {
            "id": "pi_mock",
            "status": status,
            "amountUsd": 5.0,
            "counterparty": "openai",
            "purpose": "mocked call",
        },
        "requiresApproval": status == "queued",
    }
    if status == "queued":
        payload["approval"] = {
            "id": approval_id,
            "status": "pending",
            "paymentIntentId": "pi_mock",
            "approvalUrl": f"https://nornr.com/app/approvals/{approval_id}",
        }
    return DecisionRecord.from_payload(payload)


@dataclass
class MockWallet:
    status: str = "approved"

    def pay(self, *args: Any, **kwargs: Any) -> DecisionRecord:
        return mock_decision(self.status)

    def balance(self) -> BalanceRecord:
        return BalanceRecord.from_payload({"balanceSummary": {"availableUsd": 100, "reservedUsd": 0, "pendingSettlementUsd": 0, "totalFeesUsd": 0}})

    def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload({"financePacket": {"score": 100, "openActions": [], "packetHistory": [], "lastHandoff": None}})
