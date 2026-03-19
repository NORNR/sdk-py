from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .client import AsyncWallet, Wallet


def _match_counterparty(payload: Mapping[str, Any], counterparty: str) -> bool:
    target = counterparty.strip().lower()
    candidates = [
        payload.get("name"),
        payload.get("label"),
        payload.get("counterparty"),
        payload.get("domain"),
        payload.get("id"),
    ]
    for candidate in candidates:
        if candidate and str(candidate).strip().lower() == target:
            return True
    return False


@dataclass(frozen=True)
class CounterpartyReview:
    counterparty: str
    status: str
    reasons: list[str]
    matched_profile: dict[str, Any] | None = None
    matching_anomalies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "counterparty": self.counterparty,
            "status": self.status,
            "reasons": list(self.reasons),
            "matchedProfile": dict(self.matched_profile or {}),
            "matchingAnomalies": [dict(item) for item in self.matching_anomalies],
        }


def review_counterparty(wallet: "Wallet", counterparty: str) -> CounterpartyReview:
    trust_profile = wallet.client.get_trust_profile()
    anomalies = wallet.client.list_anomalies()
    matched_profile = next(
        (item for item in trust_profile.counterparties if _match_counterparty(item, counterparty)),
        None,
    )
    matching_anomalies = [
        item.to_dict()
        for item in anomalies
        if _match_counterparty(item.to_dict(), counterparty)
    ]
    reasons: list[str] = []
    status = "approved"
    if not matched_profile:
        status = "queued"
        reasons.append("Counterparty is not present in the current trust profile.")
    if matching_anomalies:
        status = "blocked"
        reasons.append(f"{len(matching_anomalies)} anomaly signal(s) are attached to this counterparty.")
    if matched_profile:
        reasons.append("Counterparty appears in the workspace trust profile.")
    return CounterpartyReview(
        counterparty=counterparty,
        status=status,
        reasons=reasons or ["No additional posture found."],
        matched_profile=matched_profile,
        matching_anomalies=matching_anomalies,
    )


async def review_counterparty_async(wallet: "AsyncWallet", counterparty: str) -> CounterpartyReview:
    trust_profile = await wallet.client.get_trust_profile()
    anomalies = await wallet.client.list_anomalies()
    matched_profile = next(
        (item for item in trust_profile.counterparties if _match_counterparty(item, counterparty)),
        None,
    )
    matching_anomalies = [
        item.to_dict()
        for item in anomalies
        if _match_counterparty(item.to_dict(), counterparty)
    ]
    reasons: list[str] = []
    status = "approved"
    if not matched_profile:
        status = "queued"
        reasons.append("Counterparty is not present in the current trust profile.")
    if matching_anomalies:
        status = "blocked"
        reasons.append(f"{len(matching_anomalies)} anomaly signal(s) are attached to this counterparty.")
    if matched_profile:
        reasons.append("Counterparty appears in the workspace trust profile.")
    return CounterpartyReview(
        counterparty=counterparty,
        status=status,
        reasons=reasons or ["No additional posture found."],
        matched_profile=matched_profile,
        matching_anomalies=matching_anomalies,
    )
