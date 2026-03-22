from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, cast

from .auth import DEFAULT_BASE_URL, load_login
from .budgeting import BudgetContext, budget as budget_scope, current_budget_scope
from .breakers import CircuitBreakerConfig, LocalCircuitBreaker
from .context import merge_business_context
from .counterparty import CounterpartyReview, review_counterparty as review_counterparty_sync, review_counterparty_async
from .delegation import DelegatedMandate, create_delegated_mandate, create_delegated_mandate_async
from .intent import IntentCheckRecord
from .models import (
    ApprovalRecord,
    AuditReviewRecord,
    BalanceRecord,
    DecisionRecord,
    FinancePacketRecord,
    PolicyPackApplyRecord,
    PolicyPackCatalogRecord,
    PolicyPackDetailRecord,
    PolicyPackReplayResultRecord,
    PolicyPackRollbackRecord,
    PolicySimulationRecord,
    SettlementRunRecord,
    TimelineReportRecord,
    WeeklyReviewRecord,
)
from .money import AmountLike, usd_decimal, usd_float, usd_text
from .replay import merge_replay_context
from .runtime import AsyncGovernedActionRun, GovernedActionRun, GovernedExecutionRecord, default_run_ids

if TYPE_CHECKING:
    from .client import AgentPayClient, AsyncAgentPayClient
    from .transport import AsyncHttpTransport, SyncHttpTransport


def _looks_like_evm_address(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("0x") and len(value) == 42


def _first_agent(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    from .client import AgentPayError

    agents = bootstrap.get("agents") or []
    if not agents:
        raise AgentPayError("Wallet bootstrap did not return any agents")
    return cast(dict[str, Any], agents[0])


def _find_pending_approval(bootstrap: Mapping[str, Any], payment_intent_id: str) -> dict[str, Any] | None:
    approvals = bootstrap.get("approvals") or []
    return next((item for item in approvals if item.get("paymentIntentId") == payment_intent_id and item.get("status") == "pending"), None)


@dataclass
class Wallet:
    client: "AgentPayClient"
    workspace: dict[str, Any]
    agent: dict[str, Any]
    wallet: Mapping[str, Any] | None
    api_key: dict[str, Any] | None
    policy: dict[str, Any] | None = None
    circuit_breaker: LocalCircuitBreaker | None = None

    @classmethod
    def create(
        cls,
        *,
        owner: str,
        daily_limit: AmountLike = 100,
        base_url: str = DEFAULT_BASE_URL,
        workspace_name: str | None = None,
        require_approval_above: AmountLike | None = None,
        max_transaction: AmountLike | None = None,
        whitelist: list[str] | None = None,
        auto_pause_on_anomaly: bool = False,
        review_on_anomaly: bool = False,
        starting_balance: AmountLike = 100,
        timeout_seconds: float = 15.0,
        transport: "SyncHttpTransport" | None = None,
    ) -> "Wallet":
        from .client import AgentPayClient

        public_client = AgentPayClient(base_url=base_url, timeout_seconds=timeout_seconds, transport=transport)
        onboarding = public_client.onboard(
            {
                "workspaceName": workspace_name or f"{owner} workspace",
                "agentName": owner,
                "dailyLimitUsd": usd_float(daily_limit),
                "requireApprovalOverUsd": usd_float(require_approval_above) if require_approval_above is not None else None,
                "maxTransactionUsd": usd_float(max_transaction) if max_transaction is not None else None,
                "counterpartyAllowlist": whitelist,
                "autoPauseOnAnomaly": auto_pause_on_anomaly,
                "reviewOnAnomaly": review_on_anomaly,
                "startingBalanceUsd": usd_float(starting_balance),
            }
        )
        client = public_client.with_api_key(onboarding["apiKey"]["key"])
        return cls(
            client=client,
            workspace=onboarding["workspace"],
            agent=onboarding["agent"],
            wallet=onboarding.get("wallet"),
            api_key=onboarding.get("apiKey"),
            policy=onboarding.get("policy"),
        )

    @classmethod
    def connect(
        cls,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        auth_path: str | Path | None = None,
        timeout_seconds: float = 15.0,
        transport: "SyncHttpTransport" | None = None,
    ) -> "Wallet":
        from .client import AgentPayClient, AuthenticationError

        resolved_api_key = api_key
        if not resolved_api_key:
            profile = load_login(base_url=base_url, path=Path(auth_path) if auth_path else None)
            if not profile:
                raise AuthenticationError("Missing api_key and no stored NORNR login found. Run `nornr login`.")
            resolved_api_key = profile.api_key
        client = AgentPayClient(base_url=base_url, api_key=resolved_api_key, timeout_seconds=timeout_seconds, transport=transport)
        bootstrap = client.get_bootstrap()
        agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == agent_id), None) if agent_id else None
        return cls(
            client=client,
            workspace=bootstrap["workspace"],
            agent=agent or _first_agent(bootstrap),
            wallet=bootstrap.get("wallet"),
            api_key={"key": resolved_api_key},
        )

    @property
    def agent_id(self) -> str:
        return str(self.agent["id"])

    @property
    def workspace_id(self) -> str:
        return str(self.workspace["id"])

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Wallet":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def refresh(self) -> dict[str, Any]:
        bootstrap = self.client.get_bootstrap()
        self.workspace = bootstrap["workspace"]
        self.agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == self.agent_id), _first_agent(bootstrap))
        self.wallet = bootstrap.get("wallet")
        return bootstrap

    def pay(
        self,
        *,
        amount: AmountLike,
        to: str,
        purpose: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        from .client import ValidationError, _apply_business_context_tags, _control_room_url

        normalized_amount = usd_decimal(amount)
        scoped_budget = current_budget_scope()
        if scoped_budget and normalized_amount > scoped_budget.limit_usd:
            raise ValidationError(
                f"Local NORNR budget scope blocked {usd_text(normalized_amount)} USD because the block limit is {usd_text(scoped_budget.limit_usd)} USD",
            )
        if self.circuit_breaker:
            try:
                self.circuit_breaker.check(normalized_amount)
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc
        destination = to if _looks_like_evm_address(to) else None
        resolved_counterparty = counterparty or (to if not destination else "external")
        if scoped_budget and scoped_budget.counterparty and resolved_counterparty != scoped_budget.counterparty:
            raise ValidationError(
                f"Local NORNR budget scope only allows {scoped_budget.counterparty}, but got {resolved_counterparty}",
            )
        resolved_business_context = merge_business_context(business_context)
        merged_budget_tags = dict(budget_tags or {})
        if scoped_budget and scoped_budget.budget_tags:
            merged_budget_tags = {**scoped_budget.budget_tags, **merged_budget_tags}
        merged_budget_tags = _apply_business_context_tags(merged_budget_tags or None, resolved_business_context) or {}
        resolved_purpose = purpose or f"agent payment to {resolved_counterparty}"
        if scoped_budget and scoped_budget.purpose_prefix:
            resolved_purpose = f"{scoped_budget.purpose_prefix}: {resolved_purpose}"
        result = self.client.create_payment_intent(
            {
                "agentId": self.agent_id,
                "amountUsd": usd_float(normalized_amount),
                "counterparty": resolved_counterparty,
                "destination": destination,
                "budgetTags": merged_budget_tags or None,
                "purpose": resolved_purpose,
                "dryRun": bool(dry_run or (scoped_budget.dry_run if scoped_budget else False)),
                "businessContext": resolved_business_context,
                "executionContext": merge_replay_context(replay_context, default_source="wallet.pay"),
            }
        )
        payment_intent = result.get("paymentIntent") or {}
        if payment_intent.get("status") == "queued":
            bootstrap = self.client.get_bootstrap()
            approval = _find_pending_approval(bootstrap, payment_intent.get("id", ""))
            if approval:
                approval = {
                    **approval,
                    "approvalUrl": _control_room_url(self.client.base_url, approval.get("id")),
                }
                result["approval"] = approval
                result["approvalUrl"] = approval.get("approvalUrl")
            result["requiresApproval"] = approval is not None
        else:
            result["requiresApproval"] = False
        return DecisionRecord.from_payload(result)

    def pending_approvals(self) -> list[ApprovalRecord]:
        bootstrap = self.client.get_bootstrap()
        return [record for record in (ApprovalRecord.from_payload(item) for item in bootstrap.get("approvals", [])) if record and record.status == "pending"]

    def approve_if_needed(self, payment: Mapping[str, Any] | DecisionRecord, *, comment: str | None = None) -> Any:
        from .client import AgentPayError

        approval_payload = payment.get("approval") if isinstance(payment, Mapping) else None
        approval = ApprovalRecord.from_payload(approval_payload)
        if approval:
            return self.client.approve_intent(approval.id or "", {"comment": comment} if comment else {})
        payment_intent = payment.get("paymentIntent") if isinstance(payment, Mapping) else None
        status = payment_intent.get("status") if isinstance(payment_intent, Mapping) else None
        if status != "queued":
            return payment
        payment_intent_id = payment_intent.get("id") if isinstance(payment_intent, Mapping) else None
        if not payment_intent_id:
            raise AgentPayError("Queued payment is missing payment intent id")
        bootstrap = self.client.get_bootstrap()
        pending_approval = _find_pending_approval(bootstrap, str(payment_intent_id))
        if not pending_approval:
            raise AgentPayError("No pending approval found for payment intent")
        return self.client.approve_intent(pending_approval["id"], {"comment": comment} if comment else {})

    def reject(self, approval_id: str, *, comment: str | None = None) -> Any:
        return self.client.reject_intent(approval_id, {"comment": comment} if comment else {})

    def balance(self) -> BalanceRecord:
        wallet_state = self.client.get_wallet()
        self.wallet = wallet_state
        return BalanceRecord.from_payload(wallet_state)

    def settle(self) -> SettlementRunRecord:
        return self.client.run_settlement()

    def budget(
        self,
        limit: AmountLike,
        *,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> BudgetContext:
        return budget_scope(
            limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            dry_run=dry_run,
        )

    def enable_circuit_breaker(
        self,
        *,
        max_requests: int = 10,
        window_seconds: float = 1.0,
        max_spend_usd: AmountLike | None = None,
        max_velocity_usd: AmountLike | None = None,
    ) -> "Wallet":
        self.circuit_breaker = LocalCircuitBreaker(
            CircuitBreakerConfig(
                max_requests=max_requests,
                window_seconds=window_seconds,
                max_spend_usd=max_spend_usd,
                max_velocity_usd=max_velocity_usd,
            )
        )
        return self

    def guard(
        self,
        *,
        amount: AmountLike,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> Any:
        from .guards import WalletGuard

        return WalletGuard(
            self,
            amount=usd_float(amount),
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )

    def simulate_policy(self, *, template_id: str, rollout_mode: str = "shadow") -> PolicySimulationRecord:
        payload = {
            "agentId": self.agent_id,
            "templateId": template_id,
            "rolloutMode": rollout_mode,
        }
        return PolicySimulationRecord.from_payload(self.client.simulate_policy(payload))

    def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return self.client.list_policy_packs()

    def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return self.client.get_policy_pack(pack_id)

    def replay_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackReplayResultRecord:
        return self.client.replay_policy_pack(pack_id, {"agentId": self.agent_id, "mode": mode})

    def apply_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackApplyRecord:
        return self.client.apply_policy_pack(pack_id, {"agentId": self.agent_id, "mode": mode})

    def rollback_policy_pack(self, pack_id: str) -> PolicyPackRollbackRecord:
        return self.client.rollback_policy_pack(pack_id, {"agentId": self.agent_id})

    def list_policy_authoring_drafts(self, *, include_archived: bool = False) -> dict[str, Any]:
        return self.client.list_policy_authoring_drafts(include_archived=include_archived)

    def get_policy_authoring_draft(self, draft_id: str) -> dict[str, Any]:
        return self.client.get_policy_authoring_draft(draft_id)

    def replay_policy_authoring_draft(self, draft_id: str) -> Any:
        return self.client.replay_policy_authoring_draft(draft_id)

    def duplicate_policy_authoring_draft(self, draft_id: str) -> Any:
        return self.client.duplicate_policy_authoring_draft(draft_id)

    def publish_policy_authoring_draft(self, draft_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self.client.publish_policy_authoring_draft(draft_id, payload)

    def list_counterparty_profiles(self) -> list[dict[str, Any]]:
        return self.client.list_counterparty_profiles()

    def get_counterparty_profile(self, profile_id: str) -> dict[str, Any]:
        return self.client.get_counterparty_profile(profile_id)

    def compare_close_bundles(self, *, left: str, right: str) -> Any:
        return self.client.compare_close_bundles(left=left, right=right)

    def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload(self.client.get_audit_review())

    def finance_packet(self) -> FinancePacketRecord:
        return self.audit_review().finance_packet

    def timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(self.client.get_intent_timeline())

    def weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(self.client.get_weekly_review())

    def check(
        self,
        *,
        intent: str,
        cost: AmountLike,
        counterparty: str,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> IntentCheckRecord:
        normalized_cost = usd_decimal(cost)
        decision = self.pay(
            amount=normalized_cost,
            to=counterparty,
            counterparty=counterparty,
            purpose=intent,
            budget_tags=budget_tags,
            dry_run=True,
            business_context=business_context or {"reason": intent},
        )
        return IntentCheckRecord.from_decision(decision, intent=intent, amount=usd_float(normalized_cost))

    def delegate_mandate(
        self,
        *,
        target_agent_id: str,
        daily_limit: AmountLike,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        apply_budget_cap: bool = True,
    ) -> DelegatedMandate:
        return create_delegated_mandate(
            self,
            target_agent_id=target_agent_id,
            daily_limit=daily_limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            metadata=metadata,
            apply_budget_cap=apply_budget_cap,
        )

    def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return review_counterparty_sync(self, counterparty)

    def begin_governed_action(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        run_id: str | None = None,
        intent_key: str | None = None,
        idempotency_key: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> GovernedActionRun:
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        resolved_run_id, resolved_intent_key, resolved_idempotency_key = (
            run_id or generated_run_id,
            intent_key or generated_intent_key,
            idempotency_key or generated_idempotency_key,
        )
        enriched_context = {
            **dict(business_context or {}),
            "governedRun": {
                "runId": resolved_run_id,
                "intentKey": resolved_intent_key,
                "idempotencyKey": resolved_idempotency_key,
                "actionName": action_name,
            },
        }
        decision = self.pay(
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            dry_run=dry_run,
            business_context=enriched_context,
            replay_context=merge_replay_context(
                {
                    **dict(replay_context or {}),
                    "runId": resolved_run_id,
                    "intentKey": resolved_intent_key,
                    "idempotencyKey": resolved_idempotency_key,
                },
                default_source="wallet.begin_governed_action",
            ),
        )
        return GovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=decision,
            requested_amount_usd=usd_float(amount),
            requested_counterparty=counterparty or to,
            purpose=purpose,
            run_id=resolved_run_id,
            intent_key=resolved_intent_key,
            idempotency_key=resolved_idempotency_key,
            business_context=dict(enriched_context or {}),
        )

    def resume_governed_action(
        self,
        decision: DecisionRecord | Mapping[str, Any],
        *,
        action_name: str,
        amount: AmountLike | None = None,
        counterparty: str | None = None,
        purpose: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> GovernedActionRun:
        resolved = decision if isinstance(decision, DecisionRecord) else DecisionRecord.from_payload(decision)
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        return GovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=resolved,
            requested_amount_usd=usd_float(amount if amount is not None else resolved.amount_decimal),
            requested_counterparty=counterparty or resolved.payment_intent.counterparty or "unknown",
            purpose=purpose or resolved.payment_intent.purpose or action_name,
            run_id=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("runId") or generated_run_id),
            intent_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("intentKey") or generated_intent_key),
            idempotency_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("idempotencyKey") or generated_idempotency_key),
            business_context=dict(business_context or resolved.payment_intent.business_context or {}),
        )

    def execute_governed(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        callback: Any,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Any | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        run = self.begin_governed_action(
            action_name=action_name,
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            business_context=business_context,
            replay_context=replay_context,
            dry_run=dry_run,
        )
        return run.execute(callback, receipt_id=receipt_id, evidence=evidence, raise_on_error=raise_on_error)


@dataclass
class AsyncWallet:
    client: "AsyncAgentPayClient"
    workspace: dict[str, Any]
    agent: dict[str, Any]
    wallet: Mapping[str, Any] | None
    api_key: dict[str, Any] | None
    policy: dict[str, Any] | None = None
    circuit_breaker: LocalCircuitBreaker | None = None

    @classmethod
    async def create(
        cls,
        *,
        owner: str,
        daily_limit: AmountLike = 100,
        base_url: str = DEFAULT_BASE_URL,
        workspace_name: str | None = None,
        require_approval_above: AmountLike | None = None,
        max_transaction: AmountLike | None = None,
        whitelist: list[str] | None = None,
        auto_pause_on_anomaly: bool = False,
        review_on_anomaly: bool = False,
        starting_balance: AmountLike = 100,
        timeout_seconds: float = 15.0,
        transport: "AsyncHttpTransport" | None = None,
    ) -> "AsyncWallet":
        from .client import AsyncAgentPayClient

        public_client = AsyncAgentPayClient(base_url=base_url, timeout_seconds=timeout_seconds, transport=transport)
        onboarding = await public_client.onboard(
            {
                "workspaceName": workspace_name or f"{owner} workspace",
                "agentName": owner,
                "dailyLimitUsd": usd_float(daily_limit),
                "requireApprovalOverUsd": usd_float(require_approval_above) if require_approval_above is not None else None,
                "maxTransactionUsd": usd_float(max_transaction) if max_transaction is not None else None,
                "counterpartyAllowlist": whitelist,
                "autoPauseOnAnomaly": auto_pause_on_anomaly,
                "reviewOnAnomaly": review_on_anomaly,
                "startingBalanceUsd": usd_float(starting_balance),
            }
        )
        client = public_client.with_api_key(onboarding["apiKey"]["key"])
        return cls(
            client=client,
            workspace=onboarding["workspace"],
            agent=onboarding["agent"],
            wallet=onboarding.get("wallet"),
            api_key=onboarding.get("apiKey"),
            policy=onboarding.get("policy"),
        )

    @classmethod
    async def connect(
        cls,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        auth_path: str | Path | None = None,
        timeout_seconds: float = 15.0,
        transport: "AsyncHttpTransport" | None = None,
    ) -> "AsyncWallet":
        from .client import AsyncAgentPayClient, AuthenticationError

        resolved_api_key = api_key
        if not resolved_api_key:
            profile = load_login(base_url=base_url, path=Path(auth_path) if auth_path else None)
            if not profile:
                raise AuthenticationError("Missing api_key and no stored NORNR login found. Run `nornr login`.")
            resolved_api_key = profile.api_key
        client = AsyncAgentPayClient(base_url=base_url, api_key=resolved_api_key, timeout_seconds=timeout_seconds, transport=transport)
        bootstrap = await client.get_bootstrap()
        agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == agent_id), None) if agent_id else None
        return cls(
            client=client,
            workspace=bootstrap["workspace"],
            agent=agent or _first_agent(bootstrap),
            wallet=bootstrap.get("wallet"),
            api_key={"key": resolved_api_key},
        )

    @property
    def agent_id(self) -> str:
        return str(self.agent["id"])

    @property
    def workspace_id(self) -> str:
        return str(self.workspace["id"])

    async def close(self) -> None:
        await self.client.close()

    async def __aenter__(self) -> "AsyncWallet":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def refresh(self) -> dict[str, Any]:
        bootstrap = await self.client.get_bootstrap()
        self.workspace = bootstrap["workspace"]
        self.agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == self.agent_id), _first_agent(bootstrap))
        self.wallet = bootstrap.get("wallet")
        return bootstrap

    async def pay(
        self,
        *,
        amount: AmountLike,
        to: str,
        purpose: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        from .client import ValidationError, _apply_business_context_tags, _control_room_url

        normalized_amount = usd_decimal(amount)
        scoped_budget = current_budget_scope()
        if scoped_budget and normalized_amount > scoped_budget.limit_usd:
            raise ValidationError(
                f"Local NORNR budget scope blocked {usd_text(normalized_amount)} USD because the block limit is {usd_text(scoped_budget.limit_usd)} USD",
            )
        if self.circuit_breaker:
            try:
                self.circuit_breaker.check(normalized_amount)
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc
        destination = to if _looks_like_evm_address(to) else None
        resolved_counterparty = counterparty or (to if not destination else "external")
        if scoped_budget and scoped_budget.counterparty and resolved_counterparty != scoped_budget.counterparty:
            raise ValidationError(
                f"Local NORNR budget scope only allows {scoped_budget.counterparty}, but got {resolved_counterparty}",
            )
        resolved_business_context = merge_business_context(business_context)
        merged_budget_tags = dict(budget_tags or {})
        if scoped_budget and scoped_budget.budget_tags:
            merged_budget_tags = {**scoped_budget.budget_tags, **merged_budget_tags}
        merged_budget_tags = _apply_business_context_tags(merged_budget_tags or None, resolved_business_context) or {}
        resolved_purpose = purpose or f"agent payment to {resolved_counterparty}"
        if scoped_budget and scoped_budget.purpose_prefix:
            resolved_purpose = f"{scoped_budget.purpose_prefix}: {resolved_purpose}"
        result = await self.client.create_payment_intent(
            {
                "agentId": self.agent_id,
                "amountUsd": usd_float(normalized_amount),
                "counterparty": resolved_counterparty,
                "destination": destination,
                "budgetTags": merged_budget_tags or None,
                "purpose": resolved_purpose,
                "dryRun": bool(dry_run or (scoped_budget.dry_run if scoped_budget else False)),
                "businessContext": resolved_business_context,
                "executionContext": merge_replay_context(replay_context, default_source="wallet.pay.async"),
            }
        )
        payment_intent = result.get("paymentIntent") or {}
        if payment_intent.get("status") == "queued":
            bootstrap = await self.client.get_bootstrap()
            approval = _find_pending_approval(bootstrap, payment_intent.get("id", ""))
            if approval:
                approval = {
                    **approval,
                    "approvalUrl": _control_room_url(self.client.base_url, approval.get("id")),
                }
                result["approval"] = approval
                result["approvalUrl"] = approval.get("approvalUrl")
            result["requiresApproval"] = approval is not None
        else:
            result["requiresApproval"] = False
        return DecisionRecord.from_payload(result)

    async def pending_approvals(self) -> list[ApprovalRecord]:
        bootstrap = await self.client.get_bootstrap()
        return [record for record in (ApprovalRecord.from_payload(item) for item in bootstrap.get("approvals", [])) if record and record.status == "pending"]

    async def approve_if_needed(self, payment: Mapping[str, Any] | DecisionRecord, *, comment: str | None = None) -> Any:
        from .client import AgentPayError

        approval_payload = payment.get("approval") if isinstance(payment, Mapping) else None
        approval = ApprovalRecord.from_payload(approval_payload)
        if approval:
            return await self.client.approve_intent(approval.id or "", {"comment": comment} if comment else {})
        payment_intent = payment.get("paymentIntent") if isinstance(payment, Mapping) else None
        status = payment_intent.get("status") if isinstance(payment_intent, Mapping) else None
        if status != "queued":
            return payment
        payment_intent_id = payment_intent.get("id") if isinstance(payment_intent, Mapping) else None
        if not payment_intent_id:
            raise AgentPayError("Queued payment is missing payment intent id")
        bootstrap = await self.client.get_bootstrap()
        pending_approval = _find_pending_approval(bootstrap, str(payment_intent_id))
        if not pending_approval:
            raise AgentPayError("No pending approval found for payment intent")
        return await self.client.approve_intent(pending_approval["id"], {"comment": comment} if comment else {})

    async def reject(self, approval_id: str, *, comment: str | None = None) -> Any:
        return await self.client.reject_intent(approval_id, {"comment": comment} if comment else {})

    async def balance(self) -> BalanceRecord:
        wallet_state = await self.client.get_wallet()
        self.wallet = wallet_state
        return BalanceRecord.from_payload(wallet_state)

    async def settle(self) -> SettlementRunRecord:
        return await self.client.run_settlement()

    def budget(
        self,
        limit: AmountLike,
        *,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> BudgetContext:
        return budget_scope(
            limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            dry_run=dry_run,
        )

    def enable_circuit_breaker(
        self,
        *,
        max_requests: int = 10,
        window_seconds: float = 1.0,
        max_spend_usd: AmountLike | None = None,
        max_velocity_usd: AmountLike | None = None,
    ) -> "AsyncWallet":
        self.circuit_breaker = LocalCircuitBreaker(
            CircuitBreakerConfig(
                max_requests=max_requests,
                window_seconds=window_seconds,
                max_spend_usd=max_spend_usd,
                max_velocity_usd=max_velocity_usd,
            )
        )
        return self

    def guard(
        self,
        *,
        amount: AmountLike,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> Any:
        from .guards import AsyncWalletGuard

        return AsyncWalletGuard(
            self,
            amount=usd_float(amount),
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )

    async def simulate_policy(self, *, template_id: str, rollout_mode: str = "shadow") -> PolicySimulationRecord:
        return PolicySimulationRecord.from_payload(
            await self.client.simulate_policy(
                {
                    "agentId": self.agent_id,
                    "templateId": template_id,
                    "rolloutMode": rollout_mode,
                }
            )
        )

    async def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return await self.client.list_policy_packs()

    async def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return await self.client.get_policy_pack(pack_id)

    async def replay_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackReplayResultRecord:
        return await self.client.replay_policy_pack(pack_id, {"agentId": self.agent_id, "mode": mode})

    async def apply_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackApplyRecord:
        return await self.client.apply_policy_pack(pack_id, {"agentId": self.agent_id, "mode": mode})

    async def rollback_policy_pack(self, pack_id: str) -> PolicyPackRollbackRecord:
        return await self.client.rollback_policy_pack(pack_id, {"agentId": self.agent_id})

    async def list_policy_authoring_drafts(self, *, include_archived: bool = False) -> dict[str, Any]:
        return await self.client.list_policy_authoring_drafts(include_archived=include_archived)

    async def get_policy_authoring_draft(self, draft_id: str) -> dict[str, Any]:
        return await self.client.get_policy_authoring_draft(draft_id)

    async def replay_policy_authoring_draft(self, draft_id: str) -> Any:
        return await self.client.replay_policy_authoring_draft(draft_id)

    async def duplicate_policy_authoring_draft(self, draft_id: str) -> Any:
        return await self.client.duplicate_policy_authoring_draft(draft_id)

    async def publish_policy_authoring_draft(self, draft_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self.client.publish_policy_authoring_draft(draft_id, payload)

    async def list_counterparty_profiles(self) -> list[dict[str, Any]]:
        return await self.client.list_counterparty_profiles()

    async def get_counterparty_profile(self, profile_id: str) -> dict[str, Any]:
        return await self.client.get_counterparty_profile(profile_id)

    async def compare_close_bundles(self, *, left: str, right: str) -> Any:
        return await self.client.compare_close_bundles(left=left, right=right)

    async def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload(await self.client.get_audit_review())

    async def finance_packet(self) -> FinancePacketRecord:
        return (await self.audit_review()).finance_packet

    async def timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(await self.client.get_intent_timeline())

    async def weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(await self.client.get_weekly_review())

    async def check(
        self,
        *,
        intent: str,
        cost: AmountLike,
        counterparty: str,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> IntentCheckRecord:
        normalized_cost = usd_decimal(cost)
        decision = await self.pay(
            amount=normalized_cost,
            to=counterparty,
            counterparty=counterparty,
            purpose=intent,
            budget_tags=budget_tags,
            dry_run=True,
            business_context=business_context or {"reason": intent},
        )
        return IntentCheckRecord.from_decision(decision, intent=intent, amount=usd_float(normalized_cost))

    async def delegate_mandate(
        self,
        *,
        target_agent_id: str,
        daily_limit: AmountLike,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        apply_budget_cap: bool = True,
    ) -> DelegatedMandate:
        return await create_delegated_mandate_async(
            self,
            target_agent_id=target_agent_id,
            daily_limit=daily_limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            metadata=metadata,
            apply_budget_cap=apply_budget_cap,
        )

    async def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return await review_counterparty_async(self, counterparty)

    async def begin_governed_action(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        run_id: str | None = None,
        intent_key: str | None = None,
        idempotency_key: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> AsyncGovernedActionRun:
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        resolved_run_id, resolved_intent_key, resolved_idempotency_key = (
            run_id or generated_run_id,
            intent_key or generated_intent_key,
            idempotency_key or generated_idempotency_key,
        )
        enriched_context = {
            **dict(business_context or {}),
            "governedRun": {
                "runId": resolved_run_id,
                "intentKey": resolved_intent_key,
                "idempotencyKey": resolved_idempotency_key,
                "actionName": action_name,
            },
        }
        decision = await self.pay(
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            dry_run=dry_run,
            business_context=enriched_context,
            replay_context=merge_replay_context(
                {
                    **dict(replay_context or {}),
                    "runId": resolved_run_id,
                    "intentKey": resolved_intent_key,
                    "idempotencyKey": resolved_idempotency_key,
                },
                default_source="wallet.begin_governed_action.async",
            ),
        )
        return AsyncGovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=decision,
            requested_amount_usd=usd_float(amount),
            requested_counterparty=counterparty or to,
            purpose=purpose,
            run_id=resolved_run_id,
            intent_key=resolved_intent_key,
            idempotency_key=resolved_idempotency_key,
            business_context=dict(enriched_context or {}),
        )

    def resume_governed_action(
        self,
        decision: DecisionRecord | Mapping[str, Any],
        *,
        action_name: str,
        amount: AmountLike | None = None,
        counterparty: str | None = None,
        purpose: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> AsyncGovernedActionRun:
        resolved = decision if isinstance(decision, DecisionRecord) else DecisionRecord.from_payload(decision)
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        return AsyncGovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=resolved,
            requested_amount_usd=usd_float(amount if amount is not None else resolved.amount_decimal),
            requested_counterparty=counterparty or resolved.payment_intent.counterparty or "unknown",
            purpose=purpose or resolved.payment_intent.purpose or action_name,
            run_id=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("runId") or generated_run_id),
            intent_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("intentKey") or generated_intent_key),
            idempotency_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("idempotencyKey") or generated_idempotency_key),
            business_context=dict(business_context or resolved.payment_intent.business_context or {}),
        )

    async def execute_governed(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        callback: Any,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Any | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        run = await self.begin_governed_action(
            action_name=action_name,
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            business_context=business_context,
            replay_context=replay_context,
            dry_run=dry_run,
        )
        return await run.execute(callback, receipt_id=receipt_id, evidence=evidence, raise_on_error=raise_on_error)
