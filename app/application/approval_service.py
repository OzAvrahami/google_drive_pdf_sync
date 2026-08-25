"""Qt-independent approval policy and all-or-block batch orchestration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from app.application.document_repository import DocumentRepository
from app.domain.validation import ValidationResult, ValidationRules, validate_document
from app.domain.workflow_policy import (
    WorkflowAction,
    action_availability,
    can_approve_structurally,
)
from app.models.document import Document


@dataclass(frozen=True)
class ApprovalEligibility:
    can_approve: bool
    structurally_eligible: bool
    reason_codes: tuple[str, ...]
    validation: ValidationResult | None = None
    already_approved: bool = False


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    document_id: str
    reason_codes: tuple[str, ...]
    validation: ValidationResult | None = None
    already_approved: bool = False


@dataclass(frozen=True)
class BatchApprovalPlan:
    approvable_ids: tuple[str, ...]
    blocker_ids: tuple[str, ...]
    already_approved_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    ineligible_reasons: Mapping[str, tuple[str, ...]]
    validation_by_id: Mapping[str, ValidationResult]

    @property
    def blocker_count(self) -> int:
        return len(self.blocker_ids)

    @property
    def ineligible_ids(self) -> tuple[str, ...]:
        return tuple(self.ineligible_reasons)

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocker_ids)

    @property
    def can_execute(self) -> bool:
        return bool(self.approvable_ids) and not self.is_blocked


@dataclass(frozen=True)
class BatchApprovalResult:
    approved_ids: tuple[str, ...]
    plan: BatchApprovalPlan


class ApprovalService:
    """Central approval eligibility, preflight, and persistence boundary."""

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        validation_rules: ValidationRules | None = None,
    ) -> None:
        self._repository = repository
        self._validation_rules = validation_rules or ValidationRules()

    def eligibility(self, document: Document) -> ApprovalEligibility:
        if document.status == "approved":
            return ApprovalEligibility(
                False, False, ("already_approved",), already_approved=True
            )
        if not can_approve_structurally(document):
            availability = action_availability(document, WorkflowAction.APPROVE)
            return ApprovalEligibility(
                False,
                False,
                (availability.reason_code or "status_not_approvable",),
            )

        validation = validate_document(document, rules=self._validation_rules)
        if validation.has_blocking_errors:
            return ApprovalEligibility(
                False,
                True,
                tuple(dict.fromkeys(issue.code for issue in validation.blockers)),
                validation,
            )
        return ApprovalEligibility(True, True, (), validation)

    def can_approve(self, drive_file_id: str) -> ApprovalEligibility:
        document = self._repository.get_by_drive_id(drive_file_id)
        if document is None:
            return ApprovalEligibility(False, False, ("document_not_found",))
        return self.eligibility(document)

    def approve(self, drive_file_id: str) -> ApprovalResult:
        document = self._repository.get_by_drive_id(drive_file_id)
        if document is None:
            return ApprovalResult(False, drive_file_id, ("document_not_found",))
        eligibility = self.eligibility(document)
        if not eligibility.can_approve:
            return ApprovalResult(
                False,
                drive_file_id,
                eligibility.reason_codes,
                eligibility.validation,
                eligibility.already_approved,
            )

        updated = deepcopy(document)
        updated.status = "approved"
        self._repository.upsert(updated)
        return ApprovalResult(True, drive_file_id, (), eligibility.validation)

    def preflight_batch(self, drive_file_ids: Sequence[str]) -> BatchApprovalPlan:
        plan, _ = self._preflight_with_documents(drive_file_ids)
        return plan

    def approve_batch(self, drive_file_ids: Sequence[str]) -> BatchApprovalResult:
        plan, approvable_documents = self._preflight_with_documents(drive_file_ids)
        if plan.is_blocked or not approvable_documents:
            return BatchApprovalResult((), plan)

        updated_documents: list[Document] = []
        for document in approvable_documents:
            updated = deepcopy(document)
            updated.status = "approved"
            updated_documents.append(updated)
        self._repository.upsert_many(updated_documents)
        return BatchApprovalResult(
            tuple(document.drive_file_id for document in updated_documents), plan
        )

    def _preflight_with_documents(
        self, drive_file_ids: Sequence[str]
    ) -> tuple[BatchApprovalPlan, list[Document]]:
        approvable_ids: list[str] = []
        blockers: list[str] = []
        already_approved: list[str] = []
        missing: list[str] = []
        ineligible: dict[str, tuple[str, ...]] = {}
        validations: dict[str, ValidationResult] = {}
        approvable_documents: list[Document] = []

        for drive_file_id in dict.fromkeys(drive_file_ids):
            document = self._repository.get_by_drive_id(drive_file_id)
            if document is None:
                missing.append(drive_file_id)
                continue
            eligibility = self.eligibility(document)
            if eligibility.already_approved:
                already_approved.append(drive_file_id)
            elif not eligibility.structurally_eligible:
                ineligible[drive_file_id] = eligibility.reason_codes
            elif not eligibility.can_approve:
                blockers.append(drive_file_id)
                if eligibility.validation is not None:
                    validations[drive_file_id] = eligibility.validation
            else:
                approvable_ids.append(drive_file_id)
                approvable_documents.append(document)
                if eligibility.validation is not None:
                    validations[drive_file_id] = eligibility.validation

        return (
            BatchApprovalPlan(
                tuple(approvable_ids),
                tuple(blockers),
                tuple(already_approved),
                tuple(missing),
                ineligible,
                validations,
            ),
            approvable_documents,
        )
