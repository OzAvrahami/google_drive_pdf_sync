"""Application orchestration for one Workspace draft approval."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.approval_service import ApprovalResult, ApprovalService
from app.application.document_repository import DocumentRepository
from app.application.document_review_service import (
    DocumentReviewService,
    LearningFailure,
    ReviewSaveResult,
)
from app.domain.review_draft import ReviewDraft
from app.models.document import Document


@dataclass(frozen=True)
class WorkspaceApprovalResult:
    approved: bool
    document_id: str
    reason_codes: tuple[str, ...]
    document: Document | None
    corrections_saved: bool = False
    learning_failures: tuple[LearningFailure, ...] = ()
    save_result: ReviewSaveResult | None = None
    approval_result: ApprovalResult | None = None
    failure_stage: str | None = None
    error_type: str | None = None


class WorkspaceApprovalService:
    """Validate, optionally save, then approve without putting orchestration in Qt."""

    def __init__(
        self,
        repository: DocumentRepository,
        review_service: DocumentReviewService,
        approval_service: ApprovalService,
    ) -> None:
        self._repository = repository
        self._review_service = review_service
        self._approval_service = approval_service

    def approve_draft(self, draft: ReviewDraft) -> WorkspaceApprovalResult:
        document_id = draft.source_document_id
        try:
            plan = self._review_service.plan_save(draft)
        except Exception as exc:
            return WorkspaceApprovalResult(
                False,
                document_id,
                ("review_preflight_failed",),
                self._repository.get_by_drive_id(document_id),
                failure_stage="preflight",
                error_type=type(exc).__name__,
            )

        blockers = tuple(dict.fromkeys(issue.code for issue in plan.validation.blockers))
        if not plan.can_save or blockers:
            return WorkspaceApprovalResult(
                False,
                document_id,
                tuple(dict.fromkeys((*plan.reason_codes, *blockers))),
                self._repository.get_by_drive_id(document_id),
                failure_stage="preflight",
            )

        save_result: ReviewSaveResult | None = None
        if plan.requires_write:
            try:
                save_result = self._review_service.save_draft(draft)
            except Exception as exc:
                return WorkspaceApprovalResult(
                    False,
                    document_id,
                    ("save_failed",),
                    self._repository.get_by_drive_id(document_id),
                    failure_stage="save",
                    error_type=type(exc).__name__,
                )
            if not save_result.saved:
                return WorkspaceApprovalResult(
                    False,
                    document_id,
                    save_result.plan.reason_codes or ("save_failed",),
                    save_result.document,
                    save_result=save_result,
                    failure_stage="save",
                )

        corrections_saved = bool(save_result and save_result.saved)
        learning_failures = save_result.learning_failures if save_result else ()
        try:
            approval_result = self._approval_service.approve(document_id)
        except Exception as exc:
            return WorkspaceApprovalResult(
                False,
                document_id,
                ("approval_persistence_failed",),
                self._repository.get_by_drive_id(document_id),
                corrections_saved=corrections_saved,
                learning_failures=learning_failures,
                save_result=save_result,
                failure_stage="approval",
                error_type=type(exc).__name__,
            )

        return WorkspaceApprovalResult(
            approval_result.approved,
            document_id,
            approval_result.reason_codes,
            self._repository.get_by_drive_id(document_id),
            corrections_saved=corrections_saved,
            learning_failures=learning_failures,
            save_result=save_result,
            approval_result=approval_result,
            failure_stage=None if approval_result.approved else "approval",
        )
