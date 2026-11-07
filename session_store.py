"""Persistent Session State and Asynchronous Memory Consolidation.

Implements AgentOps Criterion 2:
- Cloud-native persistence connecting to Google Cloud Firestore.
- Graceful local filesystem / JSON fallback for offline development.
- Non-blocking async background tasks (asyncio.create_task) for memory consolidation.
- PII scrubbing before any persistence operation.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from config import config
from observability import get_logger, scrub_pii, trace_span

logger = get_logger("session_store")


class SessionState(BaseModel):
    """Pydantic model representing structured multi-agent conversational state."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    organization_name: Optional[str] = None
    status: str = Field(default="IN_PROGRESS")
    history: List[Dict[str, Any]] = Field(default_factory=list)
    discovered_inputs: Optional[Dict[str, Any]] = None
    readiness_assessment: Optional[Dict[str, Any]] = None
    specialist_recommendations: Optional[Dict[str, Any]] = None
    compliance_findings: Optional[List[Dict[str, Any]]] = None
    human_approval_status: str = Field(default="NONE")
    human_approval_token: Optional[str] = None
    consolidated_summary: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class SessionStore:
    """Enterprise session manager supporting Firestore with local filesystem fallback."""

    def __init__(self, project_id: Optional[str] = None, collection_name: Optional[str] = None):
        self.project_id = project_id or config.project_id
        self.collection_name = collection_name or config.firestore_collection
        self.local_dir = Path(config.local_storage_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self._firestore_client = None
        self._init_firestore()

    def _init_firestore(self) -> None:
        """Attempt to initialize Google Cloud Firestore client."""
        try:
            from google.cloud import firestore

            self._firestore_client = firestore.AsyncClient(
                project=self.project_id,
                database=config.firestore_database,
            )
            logger.info(
                "Connected to Google Cloud Firestore",
                extra={"project_id": self.project_id, "collection": self.collection_name},
            )
        except Exception as exc:
            self._firestore_client = None
            logger.warning(
                "Firestore client initialization skipped; utilizing resilient local storage fallback",
                extra={"fallback_dir": str(self.local_dir), "error": str(exc)},
            )

    @trace_span("session_store.get_session")
    async def get_session(self, session_id: str) -> SessionState:
        """Retrieve existing session state or initialize a clean one."""
        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self.collection_name).document(session_id)
                snapshot = await doc_ref.get()
                if snapshot.exists:
                    data = snapshot.to_dict()
                    return SessionState(**data)
            except Exception as exc:
                logger.warning(
                    "Firestore read error; falling back to local storage",
                    extra={"session_id": session_id, "error": str(exc)},
                )

        # Local storage fallback
        local_path = self.local_dir / f"{session_id}.json"
        if local_path.exists():
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return SessionState(**data)
            except Exception as exc:
                logger.error(f"Error reading local session file: {exc}")

        # Initialize fresh state
        fresh_state = SessionState(session_id=session_id)
        await self.save_session(fresh_state)
        return fresh_state

    @trace_span("session_store.save_session")
    async def save_session(self, session: SessionState) -> None:
        """Persist session state after sanitizing PII."""
        session.updated_at = time.time()
        raw_dict = session.model_dump()
        sanitized_dict = scrub_pii(raw_dict)

        # Try Firestore
        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self.collection_name).document(session.session_id)
                await doc_ref.set(sanitized_dict)
                return
            except Exception as exc:
                logger.warning(
                    "Firestore save failed; persisting to local storage",
                    extra={"session_id": session.session_id, "error": str(exc)},
                )

        # Local JSON write fallback
        local_path = self.local_dir / f"{session.session_id}.json"
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(sanitized_dict, f, indent=2)
        except Exception as exc:
            logger.error(f"Failed to persist local session: {exc}")

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        """Appends a sanitized conversational message to session history."""
        session = await self.get_session(session_id)
        sanitized_content = scrub_pii(content)
        session.history.append({
            "role": role,
            "content": sanitized_content,
            "timestamp": time.time(),
        })
        await self.save_session(session)

        # Proactively trigger non-blocking background consolidation if history expands
        if len(session.history) >= config.max_history_turns:
            self.schedule_background_consolidation(session_id)

    def schedule_background_consolidation(self, session_id: str) -> asyncio.Task:
        """Fires an asynchronous non-blocking background task for memory consolidation.

        Ensures that latency-sensitive agent responses and UI threads never block
        while summarization or vector indexing runs.
        """
        task = asyncio.create_task(
            self.consolidate_memory_background(session_id),
            name=f"consolidate_memory_{session_id}_{int(time.time())}",
        )
        return task

    @trace_span("session_store.consolidate_memory_background")
    async def consolidate_memory_background(self, session_id: str) -> None:
        """Background worker performing memory distillation, summarization, and state sync."""
        try:
            logger.info("Starting background memory consolidation", extra={"session_id": session_id})
            session = await self.get_session(session_id)

            if not session.history:
                return

            # Distill key architectural facts from history
            facts: List[str] = []
            if session.organization_name:
                facts.append(f"Enterprise: {session.organization_name}")
            if session.discovered_inputs:
                target = session.discovered_inputs.get("target_workloads", [])
                facts.append(f"Workloads: {target}")
            if session.readiness_assessment:
                score = session.readiness_assessment.get("overall_readiness_score")
                facts.append(f"Readiness Score: {score}/100")
            if session.specialist_recommendations:
                model = session.specialist_recommendations.get("recommended_model")
                facts.append(f"Selected Model: {model}")

            distilled_summary = " | ".join(facts) if facts else "General Onboarding Discussion"
            session.consolidated_summary = distilled_summary

            # Save consolidated state
            await self.save_session(session)
            logger.info(
                "Background memory consolidation completed successfully",
                extra={"session_id": session_id, "summary": distilled_summary},
            )
        except Exception as exc:
            logger.error(
                "Error during background memory consolidation",
                extra={"session_id": session_id, "error": str(exc)},
            )


# Global singleton instance
session_store = SessionStore()
