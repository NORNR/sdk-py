"""Generated from config/control-plane-contract.json. Do not edit by hand."""

CONTROL_PLANE_CONTRACT = {
  "rolloutModes": ("shadow", "suggested", "enforced"),
  "draftStatuses": ("draft", "candidate", "archived"),
  "emergencyModes": ("freeze", "review_only", "step_up"),
  "emergencyScopeTypes": ("workspace", "project", "agent", "counterparty", "category"),
  "approvalStatuses": ("pending", "approved", "rejected"),
  "intentStatuses": ("draft", "approved", "queued", "settled", "rejected", "failed"),
  "counterpartyVerificationStatuses": ("verified", "review_required", "blocked", "observed", "pending_review"),
  "counterpartySanctionsStatuses": ("clear", "flagged", "unknown"),
  "counterpartyRiskLevels": ("low", "medium", "high"),
  "counterpartyIdentityConfidenceLevels": ("low", "medium", "high"),
  "scopeApprovalStatuses": ("approved_for_scope", "conditional", "blocked", "review_required"),
  "bootstrapSurfaceGroups": ("core", "governance", "treasury", "trust", "reporting", "access"),
  "artifactStages": ("intent", "decision", "receipt", "close", "export"),
  "artifactFamilies": ("intent_record", "decision_record", "receipt_trail", "close_packet", "audit_export"),
  "handoffStatuses": ("operator_repair", "review_backed", "ready_to_send", "handoff_recorded", "not_recorded"),
  "trustPillars": ("vendor", "organization", "decision")
}

ROLLOUT_MODES = ("shadow", "suggested", "enforced")
DRAFT_STATUSES = ("draft", "candidate", "archived")
EMERGENCY_MODES = ("freeze", "review_only", "step_up")
EMERGENCY_SCOPE_TYPES = ("workspace", "project", "agent", "counterparty", "category")
APPROVAL_STATUSES = ("pending", "approved", "rejected")
INTENT_STATUSES = ("draft", "approved", "queued", "settled", "rejected", "failed")
COUNTERPARTY_VERIFICATION_STATUSES = ("verified", "review_required", "blocked", "observed", "pending_review")
COUNTERPARTY_SANCTIONS_STATUSES = ("clear", "flagged", "unknown")
COUNTERPARTY_RISK_LEVELS = ("low", "medium", "high")
COUNTERPARTY_IDENTITY_CONFIDENCE_LEVELS = ("low", "medium", "high")
SCOPE_APPROVAL_STATUSES = ("approved_for_scope", "conditional", "blocked", "review_required")
BOOTSTRAP_SURFACE_GROUPS = ("core", "governance", "treasury", "trust", "reporting", "access")
ARTIFACT_STAGES = ("intent", "decision", "receipt", "close", "export")
ARTIFACT_FAMILIES = ("intent_record", "decision_record", "receipt_trail", "close_packet", "audit_export")
HANDOFF_STATUSES = ("operator_repair", "review_backed", "ready_to_send", "handoff_recorded", "not_recorded")
TRUST_PILLARS = ("vendor", "organization", "decision")
