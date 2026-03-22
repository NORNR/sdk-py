from __future__ import annotations

from typing import Any, cast

from .cli_support import (
    current_month,
    load_json_payload,
    previous_month,
    print_json,
    resolve_client,
    resolve_counterparty_profile,
)


def handle_doctor_command(args: Any) -> int:
    month = args.month or current_month()
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    bootstrap = client.get_bootstrap()
    policy_packs = client.list_policy_packs().to_dict()
    compliance = client.get_compliance()
    weekly_review = client.get_weekly_review()
    close_bundle = client.get_close_bundle(month=month)
    artifact_evidence = client.get_artifact_evidence(month=month)
    audit_review = client.get_audit_review()
    intent_timeline = client.get_intent_timeline()
    counterparties = client.list_counterparty_profiles()
    authoring = client.list_policy_authoring_drafts()
    active_controls = [item for item in compliance.kill_switches if item.get("status") == "active"]
    finance_packet = dict((close_bundle or {}).get("financePacket") or {})
    packet_ready = bool(audit_review.get("proofPacket")) if isinstance(audit_review, dict) else False
    timeline_items = getattr(intent_timeline, "items", [])
    trusted_paths = len(timeline_items if isinstance(timeline_items, list) else [])
    draft_summary = authoring.get("summary", {}) if isinstance(authoring, dict) else {}
    doctor_payload = {
        "month": month,
        "baseUrl": client.base_url,
        "checks": [
            {
                "name": "bootstrap",
                "status": "ok" if bootstrap.get("workspace") else "missing",
                "detail": bootstrap.get("workspace", {}).get("name", "Workspace did not load."),
            },
            {
                "name": "policy_packs",
                "status": "ok" if policy_packs.get("packs") else "missing",
                "detail": f"{len(policy_packs.get('packs', []) or [])} named pack(s) reachable.",
            },
            {
                "name": "weekly_review",
                "status": "ok" if weekly_review.summary else "missing",
                "detail": weekly_review.summary.get("label", "Weekly review did not return summary."),
            },
            {
                "name": "first_packet",
                "status": "ok" if packet_ready else "warming",
                "detail": "Proof packet is staged." if packet_ready else "Proof packet has not been staged yet.",
            },
            {
                "name": "counterparty_memory",
                "status": "ok" if counterparties else "warming",
                "detail": f"{len(counterparties)} counterparty profile(s) recorded.",
            },
            {
                "name": "policy_authoring",
                "status": "ok" if draft_summary.get("total") else "warming",
                "detail": f"{draft_summary.get('total', 0)} draft(s) / {draft_summary.get('published', 0)} published / {draft_summary.get('recentlyReplayed', 0)} replayed.",
            },
            {
                "name": "emergency_controls",
                "status": "review" if active_controls else "ok",
                "detail": f"{len(active_controls)} active emergency control(s).",
            },
            {
                "name": "finance_close",
                "status": "ok" if finance_packet.get("readyForForwarding") else "warming",
                "detail": finance_packet.get("summary", "Finance packet is not yet ready to forward."),
            },
            {
                "name": "artifact_evidence",
                "status": "ok" if ((artifact_evidence or {}).get("manifest", {}).get("verification", {}).get("ok")) else "warming",
                "detail": (
                    f"{((artifact_evidence or {}).get('archive', {}) or {}).get('count', 0)} archived artifact(s) / "
                    f"{((artifact_evidence or {}).get('signoffs', {}) or {}).get('count', 0)} signoff(s)."
                ),
            },
            {
                "name": "trusted_paths",
                "status": "ok" if trusted_paths else "warming",
                "detail": f"{trusted_paths} governed path(s) in the intent timeline.",
            },
        ],
        "nextMove": "Prove one lane, one queue path and one defended packet before widening autonomy.",
    }
    print_json(doctor_payload)
    return 0


def handle_verify_manifest_command(args: Any) -> int:
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    if args.path:
        envelope = load_json_payload(args.path)
    else:
        envelope = client.get_signed_close_bundle_manifest(month=args.month)
    print_json({
        "envelope": envelope,
        "verification": client.verify_close_bundle_manifest(envelope),
    })
    return 0


def handle_verify_command(args: Any) -> int:
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    if args.artifact == "trust-manifest":
        envelope = load_json_payload(args.path) if args.path else client.get_signed_trust_manifest().to_dict()
        verification = client.verify_trust_manifest(envelope)
    else:
        envelope = load_json_payload(args.path) if args.path else client.get_signed_close_bundle_manifest(month=args.month)
        verification = client.verify_close_bundle_manifest(envelope)
    print_json({
        "artifact": args.artifact,
        "envelope": envelope,
        "verification": verification,
    })
    return 0


def handle_packet_diff_command(args: Any) -> int:
    left = args.left or current_month()
    right = args.right or previous_month(left)
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    comparison = client.compare_close_bundles(left=left, right=right)
    print_json({
        "months": {
            "left": left,
            "right": right,
        },
        "summary": comparison.get("summary", {}) if isinstance(comparison, dict) else {},
        "lineage": comparison.get("lineage", {}) if isinstance(comparison, dict) else {},
        "comparison": comparison,
    })
    return 0


def handle_counterparty_inspect_command(args: Any) -> int:
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    profile = resolve_counterparty_profile(client, args.profile)
    scope_approvals_raw = profile.get("scopeApprovals", [])
    watchlist_entries_raw = profile.get("watchlistEntries", [])
    dispute_history_raw = profile.get("disputeHistory", [])
    scope_approvals = cast(list[Any], scope_approvals_raw) if isinstance(scope_approvals_raw, list) else []
    watchlist_entries = cast(list[Any], watchlist_entries_raw) if isinstance(watchlist_entries_raw, list) else []
    dispute_history = cast(list[Any], dispute_history_raw) if isinstance(dispute_history_raw, list) else []
    print_json({
        "profile": profile,
        "inspection": {
            "name": profile.get("name"),
            "destination": profile.get("destination"),
            "verificationStatus": profile.get("verificationStatus"),
            "riskLevel": profile.get("riskLevel"),
            "identityConfidence": profile.get("identityConfidence"),
            "reviewCadenceDays": profile.get("reviewCadenceDays"),
            "scopeApprovals": len(scope_approvals),
            "watchlists": len(watchlist_entries),
            "openDisputes": len([entry for entry in dispute_history if isinstance(entry, dict) and entry.get("status") != "resolved"]),
        },
    })
    return 0


def handle_authoring_replay_command(args: Any) -> int:
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    print_json(client.replay_policy_authoring_draft(args.draft_id))
    return 0


def handle_authoring_publish_command(args: Any) -> int:
    client = resolve_client(args.api_key, args.base_url, args.auth_path)
    print_json(
        client.publish_policy_authoring_draft(
            args.draft_id,
            {
                "rolloutMode": args.rollout_mode,
                "publishNote": args.publish_note or "Published from NORNR CLI after replay and review.",
            },
        )
    )
    return 0
