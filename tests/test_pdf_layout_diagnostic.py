from __future__ import annotations

from app.services.pdf_corpus_service import _normalized_supplier
from scripts.diagnose_pdf_layout import (
    _normalize_mirrored_rtl_parentheses,
    _row_text,
    analyze_page_header,
    summarize,
)


def word(text: str, x0: float, x1: float, top: float) -> dict:
    return {
        "text": text,
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": top + 10,
    }


def synthetic_two_column_page(*, include_registration: bool = True) -> dict:
    words = [
        word("הקסע", 160, 180, 170.9),
        word("ןובשח", 183, 205, 170.9),
        word("ISSUERLAB", 162, 205, 232.5),
        word(":דובכל", 529, 553, 232.5),
        word("DESIGN.CONTENT.AI", 124, 205, 245.5),
        word("המגוד", 510, 531, 245.5),
        word("חוקל", 534, 553, 245.5),
        word("987654321", 485, 525, 284.5),
        word("ז.ת/פ.ח", 527, 553, 284.5),
    ]
    if include_registration:
        words.extend(
            [
                word("123456789", 120, 166, 271.5),
                word(":רוטפ", 168, 186, 271.5),
                word("קסוע", 188, 205, 271.5),
            ]
        )
    return {"page": 1, "width": 595.0, "words": words}


def test_mirrored_hebrew_parenthetical_phrase_is_reconstructed_canonically() -> None:
    assert _normalize_mirrored_rtl_parentheses(")סוכנות(") == "(סוכנות)"


def test_already_correct_hebrew_parenthetical_phrase_is_unchanged() -> None:
    assert _normalize_mirrored_rtl_parentheses("(סוכנות)") == "(סוכנות)"


def test_hebrew_legal_entity_row_reconstructs_canonical_supplier() -> None:
    raw_visual_order = [
        word('מ"עב', 104.684, 124.504, 232.501),
        word("(תונכוס)", 126.944, 158.024, 232.501),
        word("הידמ", 160.464, 179.154, 232.501),
        word("תרבח", 181.594, 204.514, 232.501),
    ]

    assert _row_text(raw_visual_order) == 'חברת מדיה (סוכנות) בע"מ'


def test_latin_candidate_is_unchanged_by_parenthesis_normalization() -> None:
    assert _normalize_mirrored_rtl_parentheses("ISSUERLAB") == "ISSUERLAB"


def test_ordinary_latin_parentheses_are_unchanged() -> None:
    assert _normalize_mirrored_rtl_parentheses("Magnezi (agency)") == "Magnezi (agency)"


def test_numeric_business_parentheses_are_unchanged() -> None:
    assert _normalize_mirrored_rtl_parentheses("Company (2026) Ltd") == "Company (2026) Ltd"


def test_canonical_supplier_comparison_remains_strict_about_parentheses() -> None:
    assert _normalized_supplier('חברת מדיה )סוכנות( בע"מ') != _normalized_supplier(
        'חברת מדיה (סוכנות) בע"מ'
    )


def test_positional_prototype_separates_issuer_and_customer_blocks() -> None:
    observations = analyze_page_header(
        synthetic_two_column_page(), current_supplier="לקוח דוגמה CUSTOMER.BRAND"
    )

    assert len(observations) == 1
    result = observations[0]
    assert result["issuer_candidate"]["text"] == "ISSUERLAB"
    assert result["customer_candidate"]["text"] == "לקוח דוגמה"
    assert result["positional_confidence"] == "high"
    assert result["proposal"] == {
        "supplier": "ISSUERLAB",
        "would_change": True,
        "evidence": result["proposal"]["evidence"],
    }


def test_prototype_does_not_propose_without_two_sided_registration_evidence() -> None:
    result = analyze_page_header(
        synthetic_two_column_page(include_registration=False),
        current_supplier="לקוח דוגמה CUSTOMER.BRAND",
    )[0]

    assert result["positional_confidence"] != "high"
    assert result["proposal"]["would_change"] is False
    assert result["proposal"]["supplier"] is None


def test_prototype_leaves_current_supplier_when_it_matches_opposite_block() -> None:
    result = analyze_page_header(
        synthetic_two_column_page(), current_supplier="ISSUERLAB"
    )[0]

    assert result["issuer_candidate"]["text"] == "ISSUERLAB"
    assert result["proposal"]["would_change"] is False


def test_summary_separates_reviewed_and_unreviewed_proposals() -> None:
    records = [
        {
            "reviewed": True,
            "current_supplier_correct": False,
            "proposal_matches_ground_truth": True,
            "source_system": "Morning",
            "pdf_engine": "mPDF",
            "layout": {"proposal": {"would_change": True}},
        },
        {
            "reviewed": True,
            "current_supplier_correct": True,
            "proposal_matches_ground_truth": None,
            "source_system": "Morning",
            "pdf_engine": "mPDF",
            "layout": {"proposal": {"would_change": False}},
        },
        {
            "reviewed": False,
            "current_supplier_correct": None,
            "proposal_matches_ground_truth": None,
            "source_system": "Unknown",
            "pdf_engine": "iText",
            "layout": {"proposal": {"would_change": True}},
        },
    ]

    result = summarize(records)

    assert result["reviewed_documents"] == 2
    assert result["reviewed_currently_correct"] == 1
    assert result["reviewed_proposed_changes"] == 1
    assert result["reviewed_proposals_matching_ground_truth"] == 1
    assert result["reviewed_proposals_mismatching_ground_truth"] == 0
    assert result["unreviewed_proposed_changes"] == 1
