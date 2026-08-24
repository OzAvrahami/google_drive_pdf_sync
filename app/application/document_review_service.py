"""Qt-independent orchestration for document review drafts and corrections."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from app.application.document_repository import DocumentRepository
from app.domain.review_draft import REVIEW_FIELDS, ReviewDraft
from app.domain.validation import (
    ValidationResult,
    ValidationRules,
    is_missing,
    parse_numeric_input,
)
from app.domain.workflow_policy import can_review_edit
from app.models.document import Document


LearningRecorder = Callable[..., str | None]

_NUMERIC_FIELDS = frozenset({"subtotal", "vat", "total"})
_LEARNING_FIELD_MAP = {
    "supplier_name": "business_name",
    "invoice_date": "invoice_date",
    "invoice_number": "invoice_number",
    "total": "amount",
}
_UNSAFE_DRAFT_ISSUES = frozenset({"invalid_number", "invalid_date"})


class DocumentNotFoundError(LookupError):
    def __init__(self, drive_file_id: str) -> None:
        self.drive_file_id = drive_file_id
        super().__init__(f"Document not found: {drive_file_id}")


@dataclass(frozen=True)
class LearningFailure:
    field_name: str
    error_type: str


@dataclass(frozen=True)
class ReviewSavePlan:
    can_save: bool
    reason_codes: tuple[str, ...]
    changed_fields: tuple[str, ...]
    corrected_data: dict[str, Any]
    was_manually_corrected: bool
    requires_write: bool
    validation: ValidationResult


@dataclass(frozen=True)
class ReviewSaveResult:
    saved: bool
    plan: ReviewSavePlan
    document: Document
    learning_failures: tuple[LearningFailure, ...] = ()


def _default_learning_recorder(**kwargs: Any) -> str | None:
    from app.services.learning_service import record_and_learn

    return record_and_learn(**kwargs)


def _normalise_value(field_name: str, value: Any) -> Any:
    if field_name in _NUMERIC_FIELDS:
        return parse_numeric_input(value)
    if is_missing(value):
        return None
    return str(value).strip()


def _equivalent(field_name: str, left: Any, right: Any) -> bool:
    try:
        return _normalise_value(field_name, left) == _normalise_value(
            field_name, right
        )
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


class DocumentReviewService:
    """Create, validate, plan, and safely persist review sessions."""

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        validation_rules: ValidationRules | None = None,
        learning_recorder: LearningRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._validation_rules = validation_rules or ValidationRules()
        self._learning_recorder = learning_recorder or _default_learning_recorder

    def load_draft(
        self,
        drive_file_id: str,
        *,
        low_confidence_fields: set[str] | frozenset[str] = frozenset(),
    ) -> ReviewDraft:
        document = self._require_document(drive_file_id)
        return ReviewDraft.from_document(
            document,
            validation_rules=self._validation_rules,
            low_confidence_fields=low_confidence_fields,
        )

    def validate_draft(self, draft: ReviewDraft) -> ValidationResult:
        return draft.validation_result

    def plan_save(self, draft: ReviewDraft) -> ReviewSavePlan:
        document = self._require_matching_document(draft)
        validation = self.validate_draft(draft)
        reasons: list[str] = []

        if document.status != draft.source_status:
            reasons.append("stale_document_status")
        if draft.source_updated_at and document.updated_at != draft.source_updated_at:
            reasons.append("stale_document_updated")

        if not can_review_edit(document):
            reasons.append("review_not_allowed")

        changed_clears = draft.changed_fields & draft.explicitly_cleared_fields
        if changed_clears:
            reasons.append("explicit_clear_not_persistable")

        if any(issue.code in _UNSAFE_DRAFT_ISSUES for issue in validation.blockers):
            reasons.append("invalid_draft_input")

        corrected_data = deepcopy(document.corrected_data)
        if not reasons:
            for field_name in draft.changed_fields:
                value = _normalise_value(field_name, draft.current_value(field_name))
                extracted = getattr(document, field_name, None)
                if _equivalent(field_name, value, extracted):
                    corrected_data.pop(field_name, None)
                else:
                    corrected_data[field_name] = value

        if draft.changed_fields:
            manually_corrected = any(
                value not in (None, "") for value in corrected_data.values()
            )
        else:
            # A no-op review must not silently normalise legacy metadata.
            manually_corrected = document.was_manually_corrected
        requires_write = not reasons and (
            corrected_data != document.corrected_data
            or manually_corrected != document.was_manually_corrected
        )
        return ReviewSavePlan(
            can_save=not reasons,
            reason_codes=tuple(dict.fromkeys(reasons)),
            changed_fields=tuple(
                field for field in REVIEW_FIELDS if field in draft.changed_fields
            ),
            corrected_data=corrected_data,
            was_manually_corrected=manually_corrected,
            requires_write=requires_write,
            validation=validation,
        )

    def save_draft(self, draft: ReviewDraft) -> ReviewSaveResult:
        document = self._require_matching_document(draft)
        plan = self.plan_save(draft)
        if not plan.can_save or not plan.requires_write:
            return ReviewSaveResult(False, plan, document)

        updated = deepcopy(document)
        updated.corrected_data = deepcopy(plan.corrected_data)
        updated.was_manually_corrected = plan.was_manually_corrected
        self._repository.upsert(updated)

        learning_failures = self._record_learning(document, updated, plan)
        return ReviewSaveResult(True, plan, updated, learning_failures)

    def _record_learning(
        self,
        original_document: Document,
        updated_document: Document,
        plan: ReviewSavePlan,
    ) -> tuple[LearningFailure, ...]:
        failures: list[LearningFailure] = []
        changed = frozenset(plan.changed_fields)
        for field_name, parser_key in _LEARNING_FIELD_MAP.items():
            if field_name not in changed:
                continue
            corrected = updated_document.corrected_data.get(field_name)
            if corrected is None:
                continue
            original = original_document.extracted_data.get(parser_key)
            original_text = str(original).strip() if original is not None else ""
            corrected_text = str(corrected).strip()
            if original_text == corrected_text:
                continue
            try:
                self._learning_recorder(
                    field_name=field_name,
                    original_value=original_text,
                    corrected_value=corrected_text,
                    drive_file_id=updated_document.drive_file_id,
                    file_name=updated_document.file_name,
                )
            except Exception as exc:
                failures.append(LearningFailure(field_name, type(exc).__name__))
        return tuple(failures)

    def _require_document(self, drive_file_id: str) -> Document:
        document = self._repository.get_by_drive_id(drive_file_id)
        if document is None:
            raise DocumentNotFoundError(drive_file_id)
        return document

    def _require_matching_document(self, draft: ReviewDraft) -> Document:
        document = self._require_document(draft.source_document_id)
        if document.id != draft.source_record_id:
            raise DocumentNotFoundError(draft.source_document_id)
        return document
