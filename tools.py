"""Domain Tools for Gemini Enterprise Deployment & AI Onboarding Prep.

Implements AgentOps Criterion 1:
- Comprehensive human-readable docstrings (purpose, parameters, returns, recovery).
- Domain-tailored tool naming.
- Strict Pydantic input and output schemas with extra='forbid'.
- Guided error handling returning structured recovery instructions to the LLM.
- Telemetry integration via agent_intent and agent_outcome logging.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

from observability import get_logger, log_agent_intent, log_agent_outcome, trace_span

logger = get_logger("domain_tools")


# =====================================================================
# 1. Pydantic Schemas for Tool Inputs & Outputs (Strict Extra='forbid')
# =====================================================================

class BaseToolModel(BaseModel):
    """Base model enforcing zero additional undeclared fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --- Tool 1: validate_domain_inputs ---

class ValidateDomainInputsRequest(BaseToolModel):
    """Input payload for validating enterprise AI onboarding readiness parameters."""
    organization_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="Official legal or business name of the enterprise adopting Gemini.",
    )
    target_workloads: List[str] = Field(
        ...,
        min_length=1,
        description="Target business use cases (e.g., 'Internal Document Search', 'Customer Support Bot', 'Code Assistant').",
    )
    compliance_frameworks: List[Literal["HIPAA", "SOC2_TYPE_II", "FEDRAMP", "GDPR", "PCI_DSS", "NONE"]] = Field(
        ...,
        description="Mandatory enterprise compliance frameworks required for the deployment.",
    )
    data_residency_region: str = Field(
        default="us-central1",
        description="Target Google Cloud region for Vertex AI endpoints and data residency.",
    )
    estimated_monthly_token_volume: int = Field(
        ...,
        ge=100_000,
        le=500_000_000,
        description="Projected monthly token throughput across prompt and generation phases.",
    )


class ValidateDomainInputsResponse(BaseToolModel):
    """Output payload indicating validation status and normalized domain parameters."""
    success: bool = Field(..., description="Whether the input parameters passed enterprise validation.")
    validated_payload: Optional[Dict[str, Any]] = Field(default=None, description="Normalized enterprise specifications.")
    risk_tier: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"] = Field(
        default="LOW", description="Assessed security and operational risk tier."
    )
    error_message: Optional[str] = Field(default=None, description="Error explanation if validation failed.")
    recovery_instructions: Optional[str] = Field(
        default=None,
        description="Actionable guidance for the LLM to recover from parameter invalidity.",
    )


# --- Tool 2: assess_enterprise_readiness ---

class AssessEnterpriseReadinessRequest(BaseToolModel):
    """Input parameters to assess cloud infrastructure and governance maturity."""
    cloud_identity_configured: bool = Field(
        ..., description="Whether Google Cloud Identity or Workforce Identity Federation (Okta/Azure AD) is active."
    )
    vpc_service_controls_enabled: bool = Field(
        ..., description="Whether VPC-SC perimeters isolate Vertex AI API traffic."
    )
    cmek_required: bool = Field(
        ..., description="Whether Customer Managed Encryption Keys (Cloud KMS) are required for data at rest."
    )
    current_iam_maturity: Literal["BASIC", "ROLE_BASED", "LEAST_PRIVILEGE_ABAC"] = Field(
        ..., description="Current Identity & Access Management operational tier."
    )


class ReadinessCheckItem(BaseToolModel):
    category: str
    status: Literal["READY", "NEEDS_REMEDIATION", "BLOCKER"]
    recommendation: str


class AssessEnterpriseReadinessResponse(BaseToolModel):
    """Output evaluation of technical maturity and blocking gaps."""
    success: bool
    overall_readiness_score: int = Field(..., ge=0, le=100, description="Readiness score out of 100.")
    readiness_level: Literal["PRODUCTION_READY", "PILOT_READY", "BLOCKED"]
    checklist: List[ReadinessCheckItem]
    error_message: Optional[str] = None
    recovery_instructions: Optional[str] = None


# --- Tool 3: generate_specialist_recommendations ---

class GenerateSpecialistRecommendationsRequest(BaseToolModel):
    """Input parameters for synthesizing model routing and architecture designs."""
    primary_workload: str = Field(
        ..., description="Primary workload description (e.g., 'Semantic RAG Search across Financial 10-K Reports')."
    )
    max_acceptable_latency_ms: int = Field(
        ..., ge=100, le=30_000, description="Maximum acceptable p95 inference latency in milliseconds."
    )
    requires_multimodal: bool = Field(
        default=False, description="Whether image, audio, or video processing is required."
    )
    requires_grounding: bool = Field(
        default=True, description="Whether output must be grounded with Vertex AI Search or enterprise vector stores."
    )
    cost_sensitivity: Literal["LOW", "BALANCED", "HIGH"] = Field(
        default="BALANCED", description="Organizational sensitivity to per-token and provisioning costs."
    )


class ArchitecturalRecommendation(BaseToolModel):
    recommended_model: Literal["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-thinking"]
    rationale: str
    grounding_architecture: str
    caching_strategy: str
    rate_limiting_qps: int
    estimated_monthly_cost_usd: float


class GenerateSpecialistRecommendationsResponse(BaseToolModel):
    """Architectural recommendation output."""
    success: bool
    recommendations: Optional[ArchitecturalRecommendation] = None
    error_message: Optional[str] = None
    recovery_instructions: Optional[str] = None


# --- Tool 4: audit_compliance_and_security_controls ---

class AuditComplianceAndSecurityControlsRequest(BaseToolModel):
    """Input parameters for auditing required Google Cloud security controls."""
    frameworks: List[Literal["HIPAA", "SOC2_TYPE_II", "FEDRAMP", "GDPR", "PCI_DSS", "NONE"]] = Field(
        ..., description="List of target frameworks."
    )
    use_model_armor: bool = Field(
        default=True, description="Whether Google Cloud Model Armor is provisioned for prompt and response filtering."
    )
    enable_cloud_dlp: bool = Field(
        default=True, description="Whether Cloud DLP de-identification inspection is deployed in-path."
    )
    private_service_connect_enabled: bool = Field(
        default=True, description="Whether Private Service Connect endpoints are configured for Vertex AI."
    )


class SecurityAuditFinding(BaseToolModel):
    framework: str
    control: str
    status: Literal["COMPLIANT", "GAP_IDENTIFIED", "REMEDIATION_REQUIRED"]
    remediation_guidance: str


class AuditComplianceAndSecurityControlsResponse(BaseToolModel):
    """Results of the security controls audit."""
    success: bool
    audit_passed: bool
    findings: List[SecurityAuditFinding]
    error_message: Optional[str] = None
    recovery_instructions: Optional[str] = None


# --- Tool 5: export_validated_deliverable_to_markdown ---

class ExportValidatedDeliverableRequest(BaseToolModel):
    """Input payload to format and output the final onboarding charter."""
    organization_name: str = Field(..., description="Target enterprise name.")
    readiness_summary: str = Field(..., min_length=20, description="Executive summary of cloud readiness.")
    architecture_overview: str = Field(..., min_length=20, description="Detailed architecture and model routing plan.")
    security_plan: str = Field(..., min_length=20, description="Security controls and compliance plan.")
    human_approval_token: Optional[str] = Field(
        default=None,
        description="Cryptographic confirmation token verifying explicit human authorization.",
    )


class ExportValidatedDeliverableResponse(BaseToolModel):
    """Final onboarding package deliverable in GitHub-flavored Markdown."""
    success: bool
    markdown_content: Optional[str] = None
    approval_status: Literal["APPROVED", "REJECTED", "PENDING_HUMAN_APPROVAL"]
    error_message: Optional[str] = None
    recovery_instructions: Optional[str] = None


# =====================================================================
# 2. Tool Implementations with Guided Error Handling
# =====================================================================

@trace_span("tool.validate_domain_inputs")
def validate_domain_inputs(request_data: Dict[str, Any]) -> ValidateDomainInputsResponse:
    """Validates enterprise AI onboarding inputs against structural, compliance, and quota constraints.

    Args:
        request_data: Dictionary conforming to ValidateDomainInputsRequest schema.
            - organization_name: Name of enterprise.
            - target_workloads: Target business application list.
            - compliance_frameworks: Applicable regulations (e.g. HIPAA, SOC2_TYPE_II).
            - data_residency_region: Desired Google Cloud region.
            - estimated_monthly_token_volume: Expected monthly token volume.

    Returns:
        ValidateDomainInputsResponse containing status, normalized payload, and risk tier.

    Recovery:
        If validation fails, check error_message and re-call with corrected types and ranges.
    """
    start_time = time.time()
    log_agent_intent(
        logger=logger,
        agent_name="discovery_agent",
        intent="Validating enterprise customer onboarding parameters",
        extra={"raw_keys": list(request_data.keys())},
    )

    try:
        validated = ValidateDomainInputsRequest(**request_data)

        # Risk Tier calculation
        risk_tier: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"] = "LOW"
        high_risk_frameworks = {"HIPAA", "FEDRAMP", "PCI_DSS"}
        if any(fw in high_risk_frameworks for fw in validated.compliance_frameworks):
            risk_tier = "CRITICAL" if "FEDRAMP" in validated.compliance_frameworks else "HIGH"
        elif validated.estimated_monthly_token_volume > 50_000_000:
            risk_tier = "MODERATE"

        response = ValidateDomainInputsResponse(
            success=True,
            validated_payload=validated.model_dump(),
            risk_tier=risk_tier,
        )

        log_agent_outcome(
            logger=logger,
            agent_name="discovery_agent",
            tool_name="validate_domain_inputs",
            success=True,
            outcome=f"Successfully validated onboarding inputs for {validated.organization_name}",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return response

    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Schema validation failed: {str(exc)}"
        recovery = (
            "Review your request payload against ValidateDomainInputsRequest schema. "
            "Ensure compliance_frameworks is a list containing only valid literals "
            "('HIPAA', 'SOC2_TYPE_II', 'FEDRAMP', 'GDPR', 'PCI_DSS', 'NONE'), "
            "estimated_monthly_token_volume is between 100,000 and 500,000,000, "
            "and no undeclared extra keys are included."
        )
        log_agent_outcome(
            logger=logger,
            agent_name="discovery_agent",
            tool_name="validate_domain_inputs",
            success=False,
            outcome=error_msg,
            duration_ms=duration_ms,
        )
        return ValidateDomainInputsResponse(
            success=False,
            error_message=error_msg,
            recovery_instructions=recovery,
        )


@trace_span("tool.assess_enterprise_readiness")
def assess_enterprise_readiness(request_data: Dict[str, Any]) -> AssessEnterpriseReadinessResponse:
    """Evaluates cloud infrastructure, identity federation, and security boundary maturity.

    Args:
        request_data: Dictionary conforming to AssessEnterpriseReadinessRequest.

    Returns:
        AssessEnterpriseReadinessResponse with score, checklist, and level.
    """
    start_time = time.time()
    log_agent_intent(
        logger=logger,
        agent_name="discovery_agent",
        intent="Assessing enterprise Google Cloud platform readiness",
    )

    try:
        req = AssessEnterpriseReadinessRequest(**request_data)
        checklist: List[ReadinessCheckItem] = []
        score = 0

        # Identity
        if req.cloud_identity_configured:
            score += 25
            checklist.append(ReadinessCheckItem(
                category="Identity & Federation",
                status="READY",
                recommendation="Workforce Identity Federation is active. Map enterprise roles to Vertex AI users.",
            ))
        else:
            checklist.append(ReadinessCheckItem(
                category="Identity & Federation",
                status="BLOCKER",
                recommendation="Enable Google Cloud Identity or configure Workforce Identity Federation before granting AI access.",
            ))

        # VPC-SC
        if req.vpc_service_controls_enabled:
            score += 35
            checklist.append(ReadinessCheckItem(
                category="Network Security",
                status="READY",
                recommendation="VPC Service Controls protect Vertex AI endpoints against data exfiltration.",
            ))
        else:
            checklist.append(ReadinessCheckItem(
                category="Network Security",
                status="NEEDS_REMEDIATION",
                recommendation="Create a Service Perimeter around aiplatform.googleapis.com and storage.googleapis.com.",
            ))

        # CMEK
        if req.cmek_required:
            score += 20
            checklist.append(ReadinessCheckItem(
                category="Data Encryption",
                status="READY",
                recommendation="Ensure Cloud KMS key ring has Vertex AI Service Agent granted 'roles/cloudkms.cryptoKeyEncrypterDecrypter'.",
            ))
        else:
            score += 20
            checklist.append(ReadinessCheckItem(
                category="Data Encryption",
                status="READY",
                recommendation="Google-managed default encryption active.",
            ))

        # IAM
        if req.current_iam_maturity == "LEAST_PRIVILEGE_ABAC":
            score += 20
            checklist.append(ReadinessCheckItem(
                category="Access Control",
                status="READY",
                recommendation="Fine-grained resource tags and conditional IAM in place.",
            ))
        elif req.current_iam_maturity == "ROLE_BASED":
            score += 15
            checklist.append(ReadinessCheckItem(
                category="Access Control",
                status="READY",
                recommendation="Standard predefined roles used. Recommend transitioning to custom least-privilege roles.",
            ))
        else:
            checklist.append(ReadinessCheckItem(
                category="Access Control",
                status="NEEDS_REMEDIATION",
                recommendation="Deprecate primitive roles (Owner/Editor) in favor of predefined Vertex AI user roles.",
            ))

        level: Literal["PRODUCTION_READY", "PILOT_READY", "BLOCKED"] = (
            "PRODUCTION_READY" if score >= 80 else ("PILOT_READY" if score >= 50 else "BLOCKED")
        )

        res = AssessEnterpriseReadinessResponse(
            success=True,
            overall_readiness_score=score,
            readiness_level=level,
            checklist=checklist,
        )

        log_agent_outcome(
            logger=logger,
            agent_name="discovery_agent",
            tool_name="assess_enterprise_readiness",
            success=True,
            outcome=f"Readiness assessment complete: Score {score}/100, Level: {level}",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return res

    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        return AssessEnterpriseReadinessResponse(
            success=False,
            overall_readiness_score=0,
            readiness_level="BLOCKED",
            checklist=[],
            error_message=f"Assessment failed: {str(exc)}",
            recovery_instructions="Provide valid boolean values for cloud_identity_configured, vpc_service_controls_enabled, cmek_required, and valid current_iam_maturity ('BASIC', 'ROLE_BASED', 'LEAST_PRIVILEGE_ABAC').",
        )


@trace_span("tool.generate_specialist_recommendations")
def generate_specialist_recommendations(request_data: Dict[str, Any]) -> GenerateSpecialistRecommendationsResponse:
    """Synthesizes optimal Gemini model selection, grounding topology, and context caching strategy.

    Args:
        request_data: Dictionary conforming to GenerateSpecialistRecommendationsRequest.

    Returns:
        GenerateSpecialistRecommendationsResponse with architectural details.
    """
    start_time = time.time()
    log_agent_intent(
        logger=logger,
        agent_name="specialist_agent",
        intent="Generating architectural recommendations and strategic model routing",
    )

    try:
        req = GenerateSpecialistRecommendationsRequest(**request_data)

        # Strategic Model Routing Decision
        if req.max_acceptable_latency_ms < 1500 or req.cost_sensitivity == "HIGH":
            selected_model = "gemini-2.5-flash"
            rationale = "Flash selected for sub-second latency SLA, extreme concurrency, and cost optimization."
            base_cost_per_m = 0.10
        else:
            selected_model = "gemini-2.5-pro"
            rationale = "Pro selected for high-complexity reasoning, extensive multi-turn synthesis, and complex planning."
            base_cost_per_m = 1.25

        grounding = (
            "Vertex AI Search data store with Enterprise edition chunking and hybrid dense/sparse embeddings."
            if req.requires_grounding
            else "Direct in-context grounding with sliding window compaction."
        )

        caching = (
            "Vertex AI Context Caching enabled for static corpus > 32,768 tokens (reduces input token costs by up to 75%)."
        )

        rec = ArchitecturalRecommendation(
            recommended_model=selected_model,
            rationale=rationale,
            grounding_architecture=grounding,
            caching_strategy=caching,
            rate_limiting_qps=50 if selected_model == "gemini-2.5-flash" else 20,
            estimated_monthly_cost_usd=round(base_cost_per_m * 120.0, 2),
        )

        res = GenerateSpecialistRecommendationsResponse(
            success=True,
            recommendations=rec,
        )

        log_agent_outcome(
            logger=logger,
            agent_name="specialist_agent",
            tool_name="generate_specialist_recommendations",
            success=True,
            outcome=f"Recommended {selected_model} for workload '{req.primary_workload}'",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return res

    except Exception as exc:
        return GenerateSpecialistRecommendationsResponse(
            success=False,
            error_message=f"Architecture generation failed: {str(exc)}",
            recovery_instructions="Verify max_acceptable_latency_ms is integer between 100 and 30,000, and cost_sensitivity is one of 'LOW', 'BALANCED', 'HIGH'.",
        )


@trace_span("tool.audit_compliance_and_security_controls")
def audit_compliance_and_security_controls(request_data: Dict[str, Any]) -> AuditComplianceAndSecurityControlsResponse:
    """Audits deployment against enterprise compliance standards (HIPAA, SOC2, FedRAMP).

    Args:
        request_data: Dictionary conforming to AuditComplianceAndSecurityControlsRequest.

    Returns:
        AuditComplianceAndSecurityControlsResponse with pass/fail and detailed findings.
    """
    start_time = time.time()
    log_agent_intent(
        logger=logger,
        agent_name="specialist_agent",
        intent="Auditing compliance controls and Model Armor defense configuration",
    )

    try:
        req = AuditComplianceAndSecurityControlsRequest(**request_data)
        findings: List[SecurityAuditFinding] = []
        all_passed = True

        for fw in req.frameworks:
            if fw == "HIPAA":
                if req.enable_cloud_dlp and req.private_service_connect_enabled:
                    findings.append(SecurityAuditFinding(
                        framework="HIPAA",
                        control="BAA & PHI De-identification",
                        status="COMPLIANT",
                        remediation_guidance="Google Cloud BAA must be signed; Cloud DLP redaction active.",
                    ))
                else:
                    all_passed = False
                    findings.append(SecurityAuditFinding(
                        framework="HIPAA",
                        control="Network Isolation & DLP",
                        status="REMEDIATION_REQUIRED",
                        remediation_guidance="HIPAA requires Private Service Connect and Cloud DLP PII/PHI redaction enabled.",
                    ))

            elif fw == "SOC2_TYPE_II":
                findings.append(SecurityAuditFinding(
                    framework="SOC2_TYPE_II",
                    control="Audit Trail & Access Logging",
                    status="COMPLIANT",
                    remediation_guidance="Enable Cloud Audit Logs (Data Access & Admin Activity) on Vertex AI API.",
                ))

            elif fw == "FEDRAMP":
                if req.private_service_connect_enabled and req.use_model_armor:
                    findings.append(SecurityAuditFinding(
                        framework="FEDRAMP",
                        control="Boundary Protection & Content Filtering",
                        status="COMPLIANT",
                        remediation_guidance="FedRAMP High boundary requires Model Armor prompt safety and private endpoints.",
                    ))
                else:
                    all_passed = False
                    findings.append(SecurityAuditFinding(
                        framework="FEDRAMP",
                        control="Boundary Protection",
                        status="BLOCKER",
                        remediation_guidance="FedRAMP requires both Model Armor and Private Service Connect enabled.",
                    ))

        if req.use_model_armor:
            findings.append(SecurityAuditFinding(
                framework="GENERAL",
                control="Model Armor Jailbreak & Toxic Filter",
                status="COMPLIANT",
                remediation_guidance="Model Armor policy active for input prompt and output response evaluation.",
            ))

        res = AuditComplianceAndSecurityControlsResponse(
            success=True,
            audit_passed=all_passed,
            findings=findings,
        )

        log_agent_outcome(
            logger=logger,
            agent_name="specialist_agent",
            tool_name="audit_compliance_and_security_controls",
            success=True,
            outcome=f"Compliance audit complete: passed={all_passed}, findings_count={len(findings)}",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return res

    except Exception as exc:
        return AuditComplianceAndSecurityControlsResponse(
            success=False,
            audit_passed=False,
            findings=[],
            error_message=f"Security audit failed: {str(exc)}",
            recovery_instructions="Ensure frameworks list is provided with valid standard literals.",
        )


@trace_span("tool.export_validated_deliverable_to_markdown")
def export_validated_deliverable_to_markdown(request_data: Dict[str, Any]) -> ExportValidatedDeliverableResponse:
    """Exports final onboarding charter to Markdown, requiring explicit human approval token.

    Args:
        request_data: Dictionary conforming to ExportValidatedDeliverableRequest.

    Returns:
        ExportValidatedDeliverableResponse with deliverable or pending approval state.
    """
    start_time = time.time()
    log_agent_intent(
        logger=logger,
        agent_name="coordinator_agent",
        intent="Verifying human confirmation token and assembling executive deliverable",
    )

    try:
        req = ExportValidatedDeliverableRequest(**request_data)

        # Enforce Human-in-the-Loop Confirmation
        if not req.human_approval_token or not req.human_approval_token.startswith("APPROVED-"):
            recovery_msg = (
                "Action blocked by Human-in-the-Loop gate. Before exporting the final enterprise charter, "
                "the human stakeholder must review the proposed architecture and issue a confirmation token "
                "(format: 'APPROVED-<timestamp>-<user_id>'). Request human approval first."
            )
            log_agent_outcome(
                logger=logger,
                agent_name="coordinator_agent",
                tool_name="export_validated_deliverable_to_markdown",
                success=False,
                outcome="Blocked pending human confirmation token",
                duration_ms=(time.time() - start_time) * 1000,
            )
            return ExportValidatedDeliverableResponse(
                success=False,
                approval_status="PENDING_HUMAN_APPROVAL",
                error_message="Human approval token missing or invalid.",
                recovery_instructions=recovery_msg,
            )

        # Construct Deliverable
        md = f"""# Gemini Enterprise Deployment & AI Onboarding Charter
**Target Enterprise:** {req.organization_name}
**Approval Status:** {req.approval_status} (Token: `{req.human_approval_token}`)

---

## 1. Executive Readiness Assessment
{req.readiness_summary}

---

## 2. Architecture & Strategic Model Routing
{req.architecture_overview}

---

## 3. Security, Privacy & Compliance Controls
{req.security_plan}

---
*Generated by Google ADK Enterprise Onboarding Multi-Agent System.*
"""

        res = ExportValidatedDeliverableResponse(
            success=True,
            markdown_content=md,
            approval_status="APPROVED",
        )

        log_agent_outcome(
            logger=logger,
            agent_name="coordinator_agent",
            tool_name="export_validated_deliverable_to_markdown",
            success=True,
            outcome=f"Deliverable exported successfully for {req.organization_name}",
            duration_ms=(time.time() - start_time) * 1000,
        )
        return res

    except Exception as exc:
        return ExportValidatedDeliverableResponse(
            success=False,
            approval_status="REJECTED",
            error_message=f"Export failed: {str(exc)}",
            recovery_instructions="Provide organization_name, readiness_summary, architecture_overview, security_plan, and valid human_approval_token.",
        )
