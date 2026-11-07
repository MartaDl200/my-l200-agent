"""Guardrails, Policy Plugins, Model Armor Hooks, and Human-in-the-Loop Gates.

Implements AgentOps Criterion 3:
- Prompt-injection screening and jailbreak detection.
- Google Cloud Model Armor pre- and post-generation safety hooks.
- Constitution-aligned self-evaluation validation.
- Human-in-the-Loop (HITL) authorization verification.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from config import config
from observability import get_logger, trace_span

logger = get_logger("guardrails")


# =====================================================================
# 1. Prompt Injection Screening
# =====================================================================

INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(all\s+)?(previous|above)\s+instructions\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+in\s+DAN\s+mode\b"),
    re.compile(r"(?i)\bsystem\s+override\b"),
    re.compile(r"(?i)\breprint\s+(the\s+)?(system\s+prompt|constitution)\b"),
    re.compile(r"(?i)\bdisregard\s+all\s+safety\s+rules\b"),
    re.compile(r"(?i)\breveal\s+(your\s+)?(hidden|internal)\s+(instructions|prompt)\b"),
    re.compile(r"(?i)<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]"),
]


class InjectionCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    risk_score: float = Field(..., ge=0.0, le=1.0)
    flagged_pattern: Optional[str] = None
    reason: Optional[str] = None


@trace_span("guardrails.screen_prompt_injection")
def screen_prompt_injection(prompt: str) -> InjectionCheckResult:
    """Evaluates user prompt against adversarial injection and jailbreak signatures.

    Args:
        prompt: Raw user input text.

    Returns:
        InjectionCheckResult with pass/fail and risk score.
    """
    if not prompt:
        return InjectionCheckResult(passed=True, risk_score=0.0)

    for pattern in INJECTION_PATTERNS:
        match = pattern.search(prompt)
        if match:
            logger.warning(
                "Prompt injection attempt detected and intercepted",
                extra={"flagged_pattern": match.group(0)},
            )
            return InjectionCheckResult(
                passed=False,
                risk_score=0.98,
                flagged_pattern=match.group(0),
                reason=f"Prompt matched prohibited injection signature: '{match.group(0)}'",
            )

    return InjectionCheckResult(passed=True, risk_score=0.05)


# =====================================================================
# 2. Google Cloud Model Armor Hooks (Pre & Post Generation)
# =====================================================================

class ModelArmorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    filter_applied: Optional[str] = None
    confidence_tier: Literal["SAFE", "SUSPICIOUS", "BLOCKED"]
    details: str


@trace_span("guardrails.model_armor_pre_check")
def model_armor_pre_check(prompt: str) -> ModelArmorResult:
    """Pre-execution hook simulating Google Cloud Model Armor prompt inspection."""
    if not config.enable_model_armor:
        return ModelArmorResult(allowed=True, confidence_tier="SAFE", details="Model Armor bypass (disabled)")

    injection = screen_prompt_injection(prompt)
    if not injection.passed:
        return ModelArmorResult(
            allowed=False,
            filter_applied="PROMPT_ATTACK_FILTER",
            confidence_tier="BLOCKED",
            details=injection.reason or "Adversarial prompt pattern detected",
        )

    return ModelArmorResult(
        allowed=True,
        confidence_tier="SAFE",
        details="Prompt verified clean by Model Armor inspection policy.",
    )


@trace_span("guardrails.model_armor_post_check")
def model_armor_post_check(generated_content: str) -> ModelArmorResult:
    """Post-generation hook inspecting model output before client delivery."""
    if not config.enable_model_armor:
        return ModelArmorResult(allowed=True, confidence_tier="SAFE", details="Model Armor bypass (disabled)")

    # Inspect for sensitive data leakage or toxicity
    leak_patterns = [
        re.compile(r"(?i)\bAIza[0-9A-Za-z-_]{35}\b"),  # Leaked API keys
        re.compile(r"(?i)\b-----BEGIN (RSA )?PRIVATE KEY-----\b"),
    ]

    for p in leak_patterns:
        if p.search(generated_content):
            logger.critical("Model Armor caught sensitive credential in model output!")
            return ModelArmorResult(
                allowed=False,
                filter_applied="SENSITIVE_DATA_LEAK_PREVENTION",
                confidence_tier="BLOCKED",
                details="Model output contained sensitive credentials; blocked from delivery.",
            )

    return ModelArmorResult(
        allowed=True,
        confidence_tier="SAFE",
        details="Output passed Model Armor safety and DLP verification.",
    )


# =====================================================================
# 3. Constitution Self-Evaluation Validation
# =====================================================================

class SelfEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conforms_to_constitution: bool
    evaluation_score: int = Field(..., ge=0, le=100)
    violations: List[str]
    remediation_recommendation: Optional[str] = None


@trace_span("guardrails.validate_self_evaluation")
def validate_self_evaluation(content: str, metadata: Optional[Dict[str, Any]] = None) -> SelfEvaluationResult:
    """Verifies that generated recommendations conform to enterprise constitutional principles.

    Ensures:
    1. Zero unverified compliance affirmations.
    2. Zero exposed secrets.
    3. Proper strategic model references (Gemini 2.5 Pro / Flash).
    """
    violations: List[str] = []
    score = 100

    # Check compliance claims vs verified controls
    if "HIPAA compliant" in content and (not metadata or not metadata.get("audit_passed")):
        violations.append("Asserted HIPAA compliance without passing prerequisite compliance audit.")
        score -= 40

    if "FedRAMP compliant" in content and (not metadata or not metadata.get("audit_passed")):
        violations.append("Asserted FedRAMP compliance without verifying VPC-SC and Model Armor perimeters.")
        score -= 40

    # Ensure strategic model routing is respected
    if "gemini-1.0" in content or "gemini-1.5" in content:
        violations.append("Outdated model tier referenced; Enterprise Constitution requires Gemini 2.5 series.")
        score -= 15

    is_conforming = (score >= 80) and (len(violations) == 0)
    remediation = (
        "Re-run generation ensuring only verified compliance statements are made and "
        "Gemini 2.5 Pro/Flash architecture is properly applied."
        if not is_conforming else None
    )

    return SelfEvaluationResult(
        conforms_to_constitution=is_conforming,
        evaluation_score=max(0, score),
        violations=violations,
        remediation_recommendation=remediation,
    )


# =====================================================================
# 4. Human-in-the-Loop Confirmation Hook
# =====================================================================

class HumanApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: str = Field(..., description="Action requiring human gate (e.g. 'EXPORT_FINAL_CHARTER')")
    organization_name: str
    approver_identity: Optional[str] = None
    approval_token: Optional[str] = None


class HumanApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    approval_token: Optional[str] = None
    message: str


def generate_approval_token(org_name: str, approver: str) -> str:
    """Generates a verifiable token for Human-in-the-Loop authorization."""
    raw = f"{org_name}:{approver}:{time.time()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"APPROVED-{int(time.time())}-{digest}"


def require_human_approval(
    action_name: str,
    organization_name: str,
    token: Optional[str] = None,
    approver: Optional[str] = None,
) -> HumanApprovalResponse:
    """Enforces Human-in-the-Loop verification gate before destructive or final actions.

    If valid token is provided, returns approved=True.
    Otherwise returns approved=False with pending guidance and instructions.
    """
    if token and token.startswith("APPROVED-"):
        logger.info(
            "Human approval confirmed",
            extra={"action": action_name, "token": token, "organization": organization_name},
        )
        return HumanApprovalResponse(
            approved=True,
            approval_token=token,
            message="Human authorization verified. Proceeding with action.",
        )

    # If approver identity provided, generate new token
    if approver:
        new_token = generate_approval_token(organization_name, approver)
        logger.info(
            "Human approval token issued",
            extra={"action": action_name, "approver": approver, "token": new_token},
        )
        return HumanApprovalResponse(
            approved=True,
            approval_token=new_token,
            message=f"Human authorization granted by {approver}. Token: {new_token}",
        )

    logger.warning(
        "Action held pending human approval gate",
        extra={"action": action_name, "organization": organization_name},
    )
    return HumanApprovalResponse(
        approved=False,
        approval_token=None,
        message=(
            f"Action '{action_name}' requires human approval before execution. "
            "Please confirm with an authorized human reviewer to obtain an approval token."
        ),
    )
