"""Application boundary for resolving persisted duplicate suspicion."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from app.application.document_repository import DocumentRepository
from app.application.irrelevant_service import (
    IrrelevantReason,
    IrrelevantResult,
    IrrelevantService,
)
from app.domain.workflow_policy import WorkflowAction, action_availability
from app.models.document import Document


@dataclass(frozen=True)
class DuplicateResolutionResult:
    succeeded: bool
    document_id: str
    action: str
    reason_code: str | None
    document: Document | None
    candidate_document: Document | None = None
    irrelevant_result: IrrelevantResult | None = None
    error_type: str | None = None


class DuplicateResolutionService:
    """Dismiss or confirm one duplicate suspicion using stable identities."""

    def __init__(
        self,
        repository: DocumentRepository,
        irrelevant_service: IrrelevantService,
    ) -> None:
        self._repository = repository
        self._irrelevant_service = irrelevant_service

    def dismiss(
        self,
        document_id: str,
        *,
        expected_status: str | None = None,
        expected_updated_at: str | None = None,
    ) -> DuplicateResolutionResult:
        current, failure = self._preflight(
            document_id, expected_status, expected_updated_at
        )
        if failure:
            return failure
        assert current is not None
        updated = deepcopy(current)
        updated.is_duplicate_suspected = False
        updated.suspected_duplicate_of = None
        updated.duplicate_confidence = None
        try:
            self._repository.upsert(updated)
        except Exception as exc:
            return DuplicateResolutionResult(
                False,
                document_id,
                "dismiss",
                "duplicate_persistence_failed",
                current,
                error_type=type(exc).__name__,
            )
        return DuplicateResolutionResult(
            True,
            document_id,
            "dismiss",
            None,
            self._repository.get_by_drive_id(document_id) or updated,
        )

    def confirm(
        self,
        document_id: str,
        candidate_id: str,
        *,
        confirmed: bool = False,
        expected_status: str | None = None,
        expected_updated_at: str | None = None,
    ) -> DuplicateResolutionResult:
        current, failure = self._preflight(
            document_id, expected_status, expected_updated_at
        )
        if failure:
            return failure
        assert current is not None
        if not confirmed:
            return DuplicateResolutionResult(
                False, document_id, "confirm", "confirmation_required", current
            )
        if candidate_id not in tuple(current.suspected_duplicate_of or ()):
            return DuplicateResolutionResult(
                False, document_id, "confirm", "candidate_not_suspected", current
            )
        candidate = self._repository.get_by_drive_id(candidate_id)
        if candidate is None:
            return DuplicateResolutionResult(
                False, document_id, "confirm", "candidate_missing", current
            )

        irrelevant = self._irrelevant_service.mark_irrelevant(
            document_id,
            reason=IrrelevantReason.CONFIRMED_DUPLICATE,
            expected_status=current.status,
            expected_updated_at=current.updated_at,
        )
        return DuplicateResolutionResult(
            irrelevant.succeeded,
            document_id,
            "confirm",
            irrelevant.reason_code,
            irrelevant.document,
            candidate_document=candidate,
            irrelevant_result=irrelevant,
            error_type=irrelevant.error_type,
        )

    def _preflight(
        self,
        document_id: str,
        expected_status: str | None,
        expected_updated_at: str | None,
    ) -> tuple[Document | None, DuplicateResolutionResult | None]:
        current = self._repository.get_by_drive_id(document_id)
        if current is None:
            return None, DuplicateResolutionResult(
                False, document_id, "unknown", "document_not_found", None
            )
        if (
            (expected_status is not None and current.status != expected_status)
            or (
                expected_updated_at is not None
                and current.updated_at != expected_updated_at
            )
        ):
            return current, DuplicateResolutionResult(
                False, document_id, "unknown", "stale_document", current
            )
        availability = action_availability(current, WorkflowAction.RESOLVE_DUPLICATE)
        if not availability.allowed:
            reason = (
                "duplicate_not_suspected"
                if not current.is_duplicate_suspected
                else "status_not_eligible"
            )
            return current, DuplicateResolutionResult(
                False,
                document_id,
                "unknown",
                reason,
                current,
            )
        return current, None
