from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .adapters import adapter_business_context, create_langchain_tools
from .client import Wallet


@dataclass(frozen=True)
class CrewTaskConfig:
    crew_id: str | None = None
    task_id: str | None = None
    role: str | None = None
    business_context: dict[str, Any] | None = None


def create_crewai_tools(
    wallet: Wallet,
    *,
    crew_id: str | None = None,
    task_id: str | None = None,
    role: str | None = None,
    business_context: dict[str, Any] | None = None,
) -> list[Callable[..., Any]]:
    """Reuse the same governed tool surface for CrewAI-style task orchestration."""

    return list(
        create_langchain_tools(
            wallet,
            business_context={
                **crewai_business_context(crew_id=crew_id, task_id=task_id, role=role),
                **dict(business_context or {}),
            },
        )
    )


def crewai_business_context(*, crew_id: str | None = None, task_id: str | None = None, role: str | None = None) -> dict[str, Any]:
    return {
        **adapter_business_context(
            surface="agent-tool",
            framework="crewai",
            workflow="crew-task",
            role=role,
        ),
        "crewId": crew_id,
        "taskId": task_id,
    }


def create_crewai_task_tools(wallet: Wallet, config: CrewTaskConfig | Mapping[str, Any]) -> list[Callable[..., Any]]:
    if isinstance(config, CrewTaskConfig):
        resolved = config
    else:
        resolved = CrewTaskConfig(
            crew_id=config.get("crew_id") or config.get("crewId"),
            task_id=config.get("task_id") or config.get("taskId"),
            role=config.get("role"),
            business_context=dict(config.get("business_context") or config.get("businessContext") or {}),
        )
    return create_crewai_tools(
        wallet,
        crew_id=resolved.crew_id,
        task_id=resolved.task_id,
        role=resolved.role,
        business_context=resolved.business_context,
    )
