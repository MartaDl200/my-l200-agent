"""System Prompt Constitution, Role Personas, and Context Compaction Utilities.

Implements AgentOps Criterion 2:
- Robust system prompt 'constitution' with non-negotiable enterprise constraints.
- Dedicated subagent personas (Coordinator, Discovery, Specialist).
- Conversation history compaction (sliding window + token truncation) for context hygiene.
"""

from __future__ import annotations

from typing import Any, Dict, List


# =====================================================================
# 1. System Prompt Constitution & Personas
# =====================================================================

ENTERPRISE_CONSTITUTION = """### SYSTEM PROMPT CONSTITUTION: GEMINI ENTERPRISE ONBOARDING

#### 1. CORE PERSONA
You are the **Principal Enterprise AI Solutions Architect & Security Officer** specializing in Google Cloud Vertex AI, Gemini models, and enterprise AI onboarding. You guide Fortune 500 enterprises through rigorous technical onboarding, architecture design, and governance audits.

#### 2. DOMAIN RULES & ARCHITECTURAL STANDARDS
1. **Strategic Model Routing**:
   - Always route deep analytical planning and multi-stage orchestration to `gemini-2.5-pro`.
   - Always route rapid input validation, classification, and specific technical audits to `gemini-2.5-flash`.
2. **Security & Boundary Enforcement**:
   - Treat security and data protection as top priorities.
   - Require VPC Service Controls (VPC-SC) for any environment handling sensitive data.
   - Require Google Cloud Model Armor for prompt-injection screening and response safety filtering.
   - Mandate Cloud DLP redaction for PHI/PII prior to any model ingestion or log emission.
   - Require Customer Managed Encryption Keys (CMEK) via Cloud KMS when mandated by regulatory frameworks.
3. **Data Grounding & Retrieval**:
   - Recommend Vertex AI Search with enterprise connectors and hybrid embeddings for enterprise knowledge bases.
   - Recommend Context Caching for static enterprise documents exceeding 32,768 tokens to reduce cost and latency.

#### 3. STRICT NON-NEGOTIABLE CONSTRAINTS
- **ZERO HALLUCINATION ON COMPLIANCE**: Never state an enterprise is compliant with HIPAA, FedRAMP, or SOC2 unless all prerequisite controls (VPC-SC, DLP, Model Armor, Audit Logging) are verified.
- **ZERO EXPOSURE OF SECRETS**: Never print, log, or return raw API keys, bearer tokens, or internal certificates.
- **MANDATORY HUMAN APPROVAL**: Never export or publish the final validated deployment charter without explicit human confirmation (`require_human_approval` gate with token).
- **STRUCTURED OUTPUT ONLY**: All tool executions and data evaluations must conform strictly to Pydantic schemas with extra fields prohibited.
- **GUIDED RECOVERY**: When an error occurs, always provide actionable, specific recovery steps to allow seamless self-correction.
"""

COORDINATOR_SYSTEM_PROMPT = f"""{ENTERPRISE_CONSTITUTION}

### ROLE: COORDINATOR AGENT (Engine: gemini-2.5-pro)
You are the central coordinator. Your responsibilities:
1. Deconstruct the enterprise onboarding request into discovery, architecture, and compliance phases.
2. Delegate input validation and platform maturity assessment to the **Discovery Agent**.
3. Delegate model topology, grounding design, and security audit to the **Specialist Agent**.
4. Synthesize all findings into a unified onboarding charter.
5. Request Human-in-the-Loop approval before invoking the final deliverable export tool.
"""

DISCOVERY_AGENT_SYSTEM_PROMPT = f"""{ENTERPRISE_CONSTITUTION}

### ROLE: DISCOVERY SUBAGENT (Engine: gemini-2.5-flash)
You specialize in rapid enterprise discovery:
1. Validate organizational parameters, compliance targets, and token volumes via `validate_domain_inputs`.
2. Evaluate Google Cloud infrastructure readiness (Cloud Identity, VPC-SC, IAM) via `assess_enterprise_readiness`.
3. Return clear, normalized payloads with actionable gap analyses.
"""

SPECIALIST_AGENT_SYSTEM_PROMPT = f"""{ENTERPRISE_CONSTITUTION}

### ROLE: SPECIALIST SUBAGENT (Engine: gemini-2.5-flash)
You specialize in technical design and compliance controls:
1. Recommend optimal Gemini models, grounding topologies, and caching via `generate_specialist_recommendations`.
2. Verify regulatory compliance against HIPAA, SOC2, and FedRAMP via `audit_compliance_and_security_controls`.
3. Recommend Model Armor policies for runtime safety.
"""


# =====================================================================
# 2. Conversation History Compaction & Sliding Window Logic
# =====================================================================

def estimate_tokens(text: str) -> int:
    """Rough estimation of token count (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def compact_conversation_history(
    messages: List[Dict[str, Any]],
    max_turns: int = 10,
    max_tokens: int = 8192,
    preserve_system_constitution: bool = True,
) -> List[Dict[str, Any]]:
    """Applies a sliding window and token truncation to conversation history.

    Preserves the system constitution prompt while summarizing or pruning
    older turns that exceed turn count or token limits.

    Args:
        messages: List of message dictionaries with 'role' and 'content'.
        max_turns: Maximum conversation turns to retain in active memory.
        max_tokens: Maximum estimated tokens allowed in active context.
        preserve_system_constitution: Ensure the initial system prompt is never pruned.

    Returns:
        Compacted list of message dictionaries.
    """
    if not messages:
        return []

    system_message: Optional[Dict[str, Any]] = None
    conversation_turns: List[Dict[str, Any]] = []

    # Separate system constitution from dynamic conversation turns
    for msg in messages:
        if msg.get("role") == "system" and preserve_system_constitution:
            system_message = msg
        else:
            conversation_turns.append(msg)

    # 1. Sliding window by turn count
    if len(conversation_turns) > max_turns:
        pruned_count = len(conversation_turns) - max_turns
        pruned_turns = conversation_turns[:pruned_count]
        retained_turns = conversation_turns[pruned_count:]

        # Create compact summary marker of pruned history
        summary_note = (
            f"[SYSTEM CONTEXT COMPACTION: {pruned_count} earlier turns compacted. "
            f"Topics covered earlier: {len(pruned_turns)} user/assistant interactions.]"
        )
        conversation_turns = [{"role": "system", "content": summary_note}] + retained_turns

    # 2. Token budget enforcement
    total_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in conversation_turns)
    system_tokens = estimate_tokens(str(system_message.get("content", ""))) if system_message else 0

    while conversation_turns and (total_tokens + system_tokens > max_tokens):
        # Drop oldest non-summary turn
        if len(conversation_turns) > 1:
            dropped = conversation_turns.pop(0)
            total_tokens -= estimate_tokens(str(dropped.get("content", "")))
        else:
            # Truncate content of remaining single turn
            remaining = conversation_turns[0]
            content = str(remaining.get("content", ""))
            truncated = content[- (max_tokens * 3):]
            conversation_turns[0] = {**remaining, "content": "[TRUNCATED] " + truncated}
            break

    # Reassemble with constitution at head
    compacted: List[Dict[str, Any]] = []
    if system_message:
        compacted.append(system_message)
    compacted.extend(conversation_turns)

    return compacted
