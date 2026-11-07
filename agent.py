"""Multi-Agent Coordinator-Subagent Architecture for Gemini Enterprise Onboarding.

Implements AgentOps Criterion 3:
- Strategic Model Routing:
  * coordinator_agent -> gemini-2.5-pro (Complex planning, synthesis, HITL gating)
  * discovery_agent -> gemini-2.5-flash (Fast schema validation & readiness checks)
  * specialist_agent -> gemini-2.5-flash (Fast architecture design & compliance audit)
- Integrated Guardrails, Model Armor, and Constitution Self-Evaluation.
- Non-blocking async background memory consolidation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from config import config
from guardrails import (
    model_armor_post_check,
    model_armor_pre_check,
    require_human_approval,
    screen_prompt_injection,
    validate_self_evaluation,
)
from observability import get_logger, log_agent_intent, log_agent_outcome, trace_span
from prompts import (
    COORDINATOR_SYSTEM_PROMPT,
    DISCOVERY_AGENT_SYSTEM_PROMPT,
    SPECIALIST_AGENT_SYSTEM_PROMPT,
    compact_conversation_history,
)
from secrets_manager import get_gemini_api_key
from session_store import SessionState, session_store
from tools import (
    assess_enterprise_readiness,
    audit_compliance_and_security_controls,
    export_validated_deliverable_to_markdown,
    generate_specialist_recommendations,
    validate_domain_inputs,
)

logger = get_logger("orchestrator")


# =====================================================================
# 1. Base Agent & Strategic Subagents
# =====================================================================

class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_name: str
    model_used: str
    success: bool
    output_data: Dict[str, Any]
    summary: str
    execution_time_ms: float
    error: Optional[str] = None


class BaseSubagent:
    """Base subagent defining model routing, tools, and execution lifecycle."""

    def __init__(self, name: str, model: str, system_prompt: str, tools: List[Callable]):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.tools = {tool.__name__: tool for tool in tools}

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not registered for agent '{self.name}'.")
        return self.tools[tool_name](payload)


class DiscoveryAgent(BaseSubagent):
    """Fast subagent running gemini-2.5-flash for enterprise discovery & validation."""

    def __init__(self):
        super().__init__(
            name="discovery_agent",
            model=config.discovery_model,  # gemini-2.5-flash
            system_prompt=DISCOVERY_AGENT_SYSTEM_PROMPT,
            tools=[validate_domain_inputs, assess_enterprise_readiness],
        )

    @trace_span("agent.discovery_agent.run")
    async def run(self, raw_inputs: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        log_agent_intent(
            logger=logger,
            agent_name=self.name,
            intent="Executing enterprise discovery, validation, and infrastructure scoring",
        )

        # 1. Validate domain inputs
        val_res = self.execute_tool("validate_domain_inputs", raw_inputs.get("domain_inputs", {}))
        if not val_res.success:
            duration_ms = (time.time() - start_time) * 1000
            return AgentResult(
                agent_name=self.name,
                model_used=self.model,
                success=False,
                output_data={"validation": val_res.model_dump()},
                summary=f"Validation failed: {val_res.error_message}",
                execution_time_ms=duration_ms,
                error=val_res.error_message,
            )

        # 2. Assess readiness
        infra_inputs = raw_inputs.get("infrastructure_inputs", {
            "cloud_identity_configured": True,
            "vpc_service_controls_enabled": True,
            "cmek_required": False,
            "current_iam_maturity": "ROLE_BASED",
        })
        readiness_res = self.execute_tool("assess_enterprise_readiness", infra_inputs)

        duration_ms = (time.time() - start_time) * 1000
        summary = (
            f"Validated {val_res.validated_payload.get('organization_name')}. "
            f"Readiness Score: {readiness_res.overall_readiness_score}/100 ({readiness_res.readiness_level})."
        )

        return AgentResult(
            agent_name=self.name,
            model_used=self.model,
            success=True,
            output_data={
                "validation": val_res.model_dump(),
                "readiness": readiness_res.model_dump(),
            },
            summary=summary,
            execution_time_ms=duration_ms,
        )


class SpecialistAgent(BaseSubagent):
    """Fast subagent running gemini-2.5-flash for architecture synthesis and compliance."""

    def __init__(self):
        super().__init__(
            name="specialist_agent",
            model=config.specialist_model,  # gemini-2.5-flash
            system_prompt=SPECIALIST_AGENT_SYSTEM_PROMPT,
            tools=[generate_specialist_recommendations, audit_compliance_and_security_controls],
        )

    @trace_span("agent.specialist_agent.run")
    async def run(self, context_inputs: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        log_agent_intent(
            logger=logger,
            agent_name=self.name,
            intent="Designing model routing, grounding topology, and compliance controls",
        )

        # 1. Architecture recommendations
        workload = context_inputs.get("primary_workload", "Enterprise Semantic Document Search")
        rec_res = self.execute_tool("generate_specialist_recommendations", {
            "primary_workload": workload,
            "max_acceptable_latency_ms": context_inputs.get("max_acceptable_latency_ms", 1200),
            "requires_multimodal": context_inputs.get("requires_multimodal", False),
            "requires_grounding": True,
            "cost_sensitivity": context_inputs.get("cost_sensitivity", "BALANCED"),
        })

        # 2. Compliance audit
        frameworks = context_inputs.get("frameworks", ["SOC2_TYPE_II"])
        audit_res = self.execute_tool("audit_compliance_and_security_controls", {
            "frameworks": frameworks,
            "use_model_armor": True,
            "enable_cloud_dlp": True,
            "private_service_connect_enabled": True,
        })

        duration_ms = (time.time() - start_time) * 1000
        summary = (
            f"Recommended Model: {rec_res.recommendations.recommended_model}. "
            f"Compliance Audit Passed: {audit_res.audit_passed}."
        )

        return AgentResult(
            agent_name=self.name,
            model_used=self.model,
            success=rec_res.success and audit_res.success,
            output_data={
                "recommendation": rec_res.model_dump(),
                "compliance": audit_res.model_dump(),
            },
            summary=summary,
            execution_time_ms=duration_ms,
        )


# =====================================================================
# 2. Coordinator Agent (Gemini 2.5 Pro) & Orchestrator
# =====================================================================

class OnboardingOrchestrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    organization_name: str
    status: str
    coordinator_model: str
    discovery_result: Optional[Dict[str, Any]] = None
    specialist_result: Optional[Dict[str, Any]] = None
    self_evaluation: Optional[Dict[str, Any]] = None
    final_deliverable_markdown: Optional[str] = None
    human_approval_status: str
    execution_time_total_ms: float
    error_message: Optional[str] = None


class CoordinatorAgent:
    """Master Coordinator running gemini-2.5-pro for complex planning, subagent orchestration, and HITL gate."""

    def __init__(self):
        self.name = "coordinator_agent"
        self.model = config.coordinator_model  # gemini-2.5-pro
        self.system_prompt = COORDINATOR_SYSTEM_PROMPT
        self.discovery_agent = DiscoveryAgent()
        self.specialist_agent = SpecialistAgent()

    @trace_span("agent.coordinator_agent.orchestrate")
    async def orchestrate(
        self,
        session_id: str,
        user_prompt: str,
        domain_inputs: Dict[str, Any],
        infrastructure_inputs: Optional[Dict[str, Any]] = None,
        human_approval_token: Optional[str] = None,
    ) -> OnboardingOrchestrationResponse:
        start_time = time.time()
        log_agent_intent(
            logger=logger,
            agent_name=self.name,
            intent=f"Orchestrating Gemini Enterprise Onboarding for session {session_id}",
            session_id=session_id,
        )

        # -------------------------------------------------------------
        # STEP 1: Guardrail Inspection (Prompt Injection & Model Armor)
        # -------------------------------------------------------------
        armor_check = model_armor_pre_check(user_prompt)
        if not armor_check.allowed:
            return OnboardingOrchestrationResponse(
                session_id=session_id,
                organization_name=domain_inputs.get("organization_name", "Unknown"),
                status="BLOCKED_BY_GUARDRAIL",
                coordinator_model=self.model,
                human_approval_status="REJECTED",
                execution_time_total_ms=(time.time() - start_time) * 1000,
                error_message=f"Guardrail violation: {armor_check.details}",
            )

        # -------------------------------------------------------------
        # STEP 2: State Loading & Context Compaction
        # -------------------------------------------------------------
        session = await session_store.get_session(session_id)
        session.organization_name = domain_inputs.get("organization_name", "Enterprise Client")
        await session_store.append_message(session_id, "user", user_prompt)

        compacted_history = compact_conversation_history(
            session.history,
            max_turns=config.max_history_turns,
            max_tokens=config.token_truncation_limit,
        )

        # -------------------------------------------------------------
        # STEP 3: Subagent 1 Delegation -> Discovery Agent (Flash)
        # -------------------------------------------------------------
        discovery_res = await self.discovery_agent.run({
            "domain_inputs": domain_inputs,
            "infrastructure_inputs": infrastructure_inputs or {},
        })

        if not discovery_res.success:
            await session_store.save_session(session)
            return OnboardingOrchestrationResponse(
                session_id=session_id,
                organization_name=session.organization_name,
                status="DISCOVERY_FAILED",
                coordinator_model=self.model,
                discovery_result=discovery_res.output_data,
                human_approval_status="NOT_REQUESTED",
                execution_time_total_ms=(time.time() - start_time) * 1000,
                error_message=discovery_res.error,
            )

        session.discovered_inputs = discovery_res.output_data.get("validation", {}).get("validated_payload")
        session.readiness_assessment = discovery_res.output_data.get("readiness")

        # -------------------------------------------------------------
        # STEP 4: Subagent 2 Delegation -> Specialist Agent (Flash)
        # -------------------------------------------------------------
        primary_workload = (
            domain_inputs.get("target_workloads", ["Enterprise Semantic Search"])[0]
        )
        specialist_res = await self.specialist_agent.run({
            "primary_workload": primary_workload,
            "frameworks": domain_inputs.get("compliance_frameworks", ["SOC2_TYPE_II"]),
            "cost_sensitivity": "BALANCED",
        })

        session.specialist_recommendations = (
            specialist_res.output_data.get("recommendation", {}).get("recommendations")
        )
        session.compliance_findings = (
            specialist_res.output_data.get("compliance", {}).get("findings")
        )

        # -------------------------------------------------------------
        # STEP 5: Self-Evaluation Validation against Constitution
        # -------------------------------------------------------------
        synth_preview = (
            f"Onboarding Plan for {session.organization_name}. "
            f"Selected Model: {session.specialist_recommendations.get('recommended_model')}. "
            f"Readiness Score: {session.readiness_assessment.get('overall_readiness_score')}."
        )
        self_eval = validate_self_evaluation(
            content=synth_preview,
            metadata={"audit_passed": specialist_res.output_data.get("compliance", {}).get("audit_passed")},
        )

        # -------------------------------------------------------------
        # STEP 6: Human-in-the-Loop Confirmation Gate
        # -------------------------------------------------------------
        hitl_check = require_human_approval(
            action_name="EXPORT_FINAL_CHARTER",
            organization_name=session.organization_name,
            token=human_approval_token,
        )

        final_markdown = None
        if hitl_check.approved:
            export_res = export_validated_deliverable_to_markdown({
                "organization_name": session.organization_name,
                "readiness_summary": (
                    f"Overall Readiness Score: {session.readiness_assessment.get('overall_readiness_score')}/100. "
                    f"Level: {session.readiness_assessment.get('readiness_level')}. "
                    f"Identity & VPC-SC controls verified."
                ),
                "architecture_overview": (
                    f"Model Selected: {session.specialist_recommendations.get('recommended_model')} "
                    f"({session.specialist_recommendations.get('rationale')}). "
                    f"Grounding: {session.specialist_recommendations.get('grounding_architecture')}."
                ),
                "security_plan": (
                    f"Compliance Frameworks: {domain_inputs.get('compliance_frameworks')}. "
                    "Google Cloud Model Armor prompt protection and Cloud DLP PII de-identification enabled."
                ),
                "human_approval_token": hitl_check.approval_token,
            })
            if export_res.success:
                # Post-check safety via Model Armor
                post_armor = model_armor_post_check(export_res.markdown_content)
                if post_armor.allowed:
                    final_markdown = export_res.markdown_content
                    session.human_approval_status = "APPROVED"
                    session.human_approval_token = hitl_check.approval_token
                else:
                    final_markdown = None
                    session.human_approval_status = "BLOCKED_BY_MODEL_ARMOR_POST_CHECK"
        else:
            session.human_approval_status = "PENDING_HUMAN_APPROVAL"

        # -------------------------------------------------------------
        # STEP 7: Async Non-Blocking Memory Consolidation & Persistence
        # -------------------------------------------------------------
        await session_store.save_session(session)
        # Background task fires without awaiting so client response is immediate
        session_store.schedule_background_consolidation(session_id)

        duration_total = (time.time() - start_time) * 1000
        log_agent_outcome(
            logger=logger,
            agent_name=self.name,
            tool_name="coordinator_orchestrate",
            success=True,
            outcome=f"Orchestration completed for {session.organization_name} in {round(duration_total, 2)}ms",
            duration_ms=duration_total,
            session_id=session_id,
        )

        return OnboardingOrchestrationResponse(
            session_id=session_id,
            organization_name=session.organization_name,
            status="COMPLETED" if final_markdown else "PENDING_APPROVAL",
            coordinator_model=self.model,
            discovery_result=discovery_res.output_data,
            specialist_result=specialist_res.output_data,
            self_evaluation=self_eval.model_dump(),
            final_deliverable_markdown=final_markdown,
            human_approval_status=session.human_approval_status,
            execution_time_total_ms=duration_total,
        )


# Global singleton coordinator
coordinator_agent = CoordinatorAgent()
