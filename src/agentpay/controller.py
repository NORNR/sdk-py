from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .client import Wallet


def _as_float(payload: Mapping[str, Any] | None, *keys: str) -> float:
    if not payload:
        return 0.0
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return float(value)
    return 0.0


def _as_int(payload: Mapping[str, Any] | None, *keys: str) -> int:
    if not payload:
        return 0
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return int(value)
    return 0


def _roi(revenue_usd: float, spend_usd: float) -> float:
    if spend_usd <= 0:
        return 0.0
    return revenue_usd / spend_usd


@dataclass(frozen=True)
class ControllerRecommendation:
    action: str
    target_agent_id: str
    recommended_daily_limit: float
    reason: str
    confidence: float
    evidence: dict[str, Any]

    def to_budget_cap_payload(self) -> dict[str, Any]:
        return {
            "agentId": self.target_agent_id,
            "dailyLimitUsd": round(self.recommended_daily_limit, 2),
            "reason": self.reason,
            "source": "vp-of-finance-agent",
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ControllerReview:
    finance_packet_score: float
    open_actions: int
    anomaly_rate: float
    available_usd: float
    reserved_usd: float
    highlights: list[str]
    recommendations: list[ControllerRecommendation]
    roi_estimate: float = 0.0


@dataclass(frozen=True)
class AgentOutcome:
    revenue_usd: float = 0.0
    leads: int = 0
    incidents_resolved: int = 0
    tasks_completed: int = 0


class VpOfFinanceController:
    """Meta-governance helper that adjusts spend posture for other agents."""

    def __init__(self, wallet: Wallet) -> None:
        self.wallet = wallet

    def review_workspace(
        self,
        *,
        target_agent_id: str,
        current_daily_limit: float,
        minimum_limit: float = 10.0,
        maximum_limit: float = 500.0,
        outcome: AgentOutcome | None = None,
    ) -> ControllerReview:
        packet = self.wallet.finance_packet()
        weekly = self.wallet.weekly_review()
        balance = self.wallet.balance()

        finance = weekly.finance
        score = packet.score
        open_actions = len(packet.open_actions)
        anomaly_rate = _as_float(finance, "anomalyRate", "anomalyRatePct")
        available = balance.available_usd
        reserved = balance.reserved_usd
        spend_estimate = _as_float(finance, "totalSpendUsd", "spendUsd")
        outcome = outcome or AgentOutcome()
        roi_estimate = _roi(outcome.revenue_usd, spend_estimate)

        recommendations: list[ControllerRecommendation] = []
        if (score >= 80 and open_actions == 0 and anomaly_rate <= 5 and available >= current_daily_limit * 0.5) or roi_estimate >= 3:
            new_limit = min(maximum_limit, max(current_daily_limit + 20.0, current_daily_limit * 1.25))
            recommendations.append(
                ControllerRecommendation(
                    action="raise_limit",
                    target_agent_id=target_agent_id,
                    recommended_daily_limit=new_limit,
                    reason="Finance packet is healthy, approvals are quiet, and ROI or available capacity supports a wider mandate.",
                    confidence=0.78,
                    evidence={
                        "financePacketScore": score,
                        "openActions": open_actions,
                        "anomalyRate": anomaly_rate,
                        "availableUsd": available,
                        "roiEstimate": roi_estimate,
                        "outcome": outcome.__dict__,
                    },
                )
            )
        if open_actions > 0 or anomaly_rate > 10 or (outcome.revenue_usd and roi_estimate < 1):
            new_limit = max(minimum_limit, min(current_daily_limit, current_daily_limit * 0.6))
            recommendations.append(
                ControllerRecommendation(
                    action="tighten_limit",
                    target_agent_id=target_agent_id,
                    recommended_daily_limit=new_limit,
                    reason="Open finance actions, anomaly pressure, or weak ROI suggest tightening the mandate until the lane is quiet again.",
                    confidence=0.74,
                    evidence={
                        "financePacketScore": score,
                        "openActions": open_actions,
                        "anomalyRate": anomaly_rate,
                        "reservedUsd": reserved,
                        "roiEstimate": roi_estimate,
                        "outcome": outcome.__dict__,
                    },
                )
            )
        if not recommendations:
            recommendations.append(
                ControllerRecommendation(
                    action="hold_limit",
                    target_agent_id=target_agent_id,
                    recommended_daily_limit=current_daily_limit,
                    reason="Hold the current budget cap while the workspace remains within the current risk posture.",
                    confidence=0.62,
                    evidence={
                        "financePacketScore": score,
                        "openActions": open_actions,
                        "anomalyRate": anomaly_rate,
                        "roiEstimate": roi_estimate,
                        "outcome": outcome.__dict__,
                    },
                )
            )

        return ControllerReview(
            finance_packet_score=score,
            open_actions=open_actions,
            anomaly_rate=anomaly_rate,
            available_usd=available,
            reserved_usd=reserved,
            highlights=list(weekly.highlights),
            recommendations=recommendations,
            roi_estimate=roi_estimate,
        )

    def apply_recommendation(self, recommendation: ControllerRecommendation) -> Any:
        return self.wallet.client.create_budget_cap(recommendation.to_budget_cap_payload())

    def apply_best_recommendation(
        self,
        *,
        target_agent_id: str,
        current_daily_limit: float,
        minimum_limit: float = 10.0,
        maximum_limit: float = 500.0,
        outcome: AgentOutcome | None = None,
    ) -> tuple[ControllerReview, Any]:
        review = self.review_workspace(
            target_agent_id=target_agent_id,
            current_daily_limit=current_daily_limit,
            minimum_limit=minimum_limit,
            maximum_limit=maximum_limit,
            outcome=outcome,
        )
        return review, self.apply_recommendation(review.recommendations[0])


def create_controller_recommendation(
    wallet: Wallet,
    *,
    target_agent_id: str,
    current_daily_limit: float,
    minimum_limit: float = 10.0,
    maximum_limit: float = 500.0,
    outcome: AgentOutcome | None = None,
) -> ControllerReview:
    """Build a finance-controller review for another agent's budget posture."""

    return VpOfFinanceController(wallet).review_workspace(
        target_agent_id=target_agent_id,
        current_daily_limit=current_daily_limit,
        minimum_limit=minimum_limit,
        maximum_limit=maximum_limit,
        outcome=outcome,
    )
