"""Main execution entrypoint for Gemini Enterprise Deployment & AI Onboarding Prep.

Demonstrates end-to-end execution of the multi-agent system:
1. Discovery & Validation (gemini-2.5-flash)
2. Readiness & Compliance Audit (gemini-2.5-flash)
3. Architecture & Planning Synthesis (gemini-2.5-pro)
4. Human-in-the-Loop Confirmation Gate
5. Final Charter Deliverable Generation
"""

from __future__ import annotations

import asyncio
import json
import uuid

from agent import coordinator_agent
from guardrails import generate_approval_token
from observability import get_logger

logger = get_logger("main")


async def main() -> None:
    session_id = f"onboarding-session-{uuid.uuid4().hex[:8]}"
    logger.info("Initializing Gemini Enterprise AI Onboarding Pipeline", extra={"session_id": session_id})

    # Sample Enterprise Request
    sample_domain_inputs = {
        "organization_name": "Acme Global Healthcare & Financials",
        "target_workloads": [
            "Clinical Protocol Semantic Search",
            "Regulatory Compliance Query Assistant",
        ],
        "compliance_frameworks": ["HIPAA", "SOC2_TYPE_II"],
        "data_residency_region": "us-central1",
        "estimated_monthly_token_volume": 15_000_000,
    }

    sample_infra_inputs = {
        "cloud_identity_configured": True,
        "vpc_service_controls_enabled": True,
        "cmek_required": True,
        "current_iam_maturity": "ROLE_BASED",
    }

    user_prompt = (
        "We need to deploy Gemini 2.5 on Google Cloud Vertex AI for HIPAA-compliant clinical "
        "search and SOC2 financial reporting. We need full VPC Service Controls and Model Armor."
    )

    # Phase 1: Initial Run without Human Approval (HITL Gate triggers)
    logger.info("--- Phase 1: Executing Pipeline without Human Approval ---")
    resp_pending = await coordinator_agent.orchestrate(
        session_id=session_id,
        user_prompt=user_prompt,
        domain_inputs=sample_domain_inputs,
        infrastructure_inputs=sample_infra_inputs,
        human_approval_token=None,
    )

    logger.info(
        "Phase 1 Result",
        extra={
            "status": resp_pending.status,
            "human_approval_status": resp_pending.human_approval_status,
            "readiness_score": resp_pending.discovery_result.get("readiness", {}).get("overall_readiness_score"),
        },
    )

    # Phase 2: Provide Human Approval Token and Finalize
    logger.info("--- Phase 2: Simulating Human Review & Issuing Approval Token ---")
    approval_token = generate_approval_token(
        org_name=sample_domain_inputs["organization_name"],
        approver="principal-security-architect@acme.com",
    )
    logger.info(f"Generated Approval Token: {approval_token}")

    resp_approved = await coordinator_agent.orchestrate(
        session_id=session_id,
        user_prompt="Human architect reviewed the readiness assessment and approved deployment.",
        domain_inputs=sample_domain_inputs,
        infrastructure_inputs=sample_infra_inputs,
        human_approval_token=approval_token,
    )

    logger.info(
        "Phase 2 Completed Successfully",
        extra={
            "status": resp_approved.status,
            "human_approval_status": resp_approved.human_approval_status,
            "has_markdown": bool(resp_approved.final_deliverable_markdown),
            "execution_ms": resp_approved.execution_time_total_ms,
        },
    )

    if resp_approved.final_deliverable_markdown:
        print("\n" + "=" * 60)
        print("FINAL DELIVERABLE MARKDOWN CHARTER:")
        print("=" * 60)
        print(resp_approved.final_deliverable_markdown)


if __name__ == "__main__":
    asyncio.run(main())
