"""Filtering, typed sorting, and stable selection tests for Panda 2.0 queues."""

from __future__ import annotations

import os
from time import perf_counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication

from app.models.document import Document
from app.ui.models.document_filter_model import DocumentFilterProxyModel
from app.ui.models.document_table_model import DocumentColumn, DocumentRoles, DocumentTableModel
from app.ui.models.queue_policy import AttentionSegment, QueueRoute, ReadySegment
from app.ui.models.selection import restore_selected_document_ids, selected_document_ids


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _document(document_id: str, status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "2026",
        "status": status,
        "supplier_name": "Acme",
        "invoice_number": f"INV-{document_id}",
        "invoice_date": "01/01/2026",
        "total": 100.0,
        "confidence": 0.8,
    }
    values.update(overrides)
    return Document(**values)


def _proxy(documents: list[Document]) -> tuple[DocumentTableModel, DocumentFilterProxyModel]:
    model = DocumentTableModel(documents)
    proxy = DocumentFilterProxyModel()
    proxy.setSourceModel(model)
    return model, proxy


def _visible_ids(proxy: DocumentFilterProxyModel) -> list[str]:
    return [
        proxy.data(proxy.index(row, 0), DocumentRoles.DOCUMENT_ID)
        for row in range(proxy.rowCount())
    ]


@pytest.mark.parametrize(
    "route, expected",
    [
        (QueueRoute.INBOX, ["new"]),
        (QueueRoute.ATTENTION, ["review", "failed", "skipped", "duplicate"]),
        (QueueRoute.READY, ["processed", "approved"]),
        (QueueRoute.IRRELEVANT, ["irrelevant", "excluded"]),
        (QueueRoute.HISTORY, ["exported"]),
    ],
)
def test_route_filter_uses_shared_membership_policy(qapp, route, expected) -> None:
    documents = [
        _document("new", "new"),
        _document("review", "needs_review"),
        _document("failed", "failed"),
        _document("skipped", "skipped"),
        _document("duplicate", "processed", is_duplicate_suspected=True),
        _document("processed", "processed"),
        _document("approved", "approved"),
        _document("irrelevant", "confirmed_irrelevant"),
        _document("excluded", "excluded"),
        _document("exported", "exported"),
    ]
    _, proxy = _proxy(documents)

    proxy.set_route(route)

    assert _visible_ids(proxy) == expected


@pytest.mark.parametrize(
    "segment, expected",
    [
        (ReadySegment.ALL, ["processed", "corrected", "approved"]),
        (ReadySegment.READY_TO_APPROVE, ["processed", "corrected"]),
        (ReadySegment.READY_TO_EXPORT, ["approved"]),
    ],
)
def test_ready_segments_filter_derived_statuses(qapp, segment, expected) -> None:
    _, proxy = _proxy(
        [
            _document("processed"),
            _document("corrected", was_manually_corrected=True),
            _document("approved", "approved"),
            _document("review", "needs_review"),
        ]
    )
    proxy.set_route(QueueRoute.READY)
    proxy.set_ready_segment(segment)

    assert _visible_ids(proxy) == expected


def test_manually_corrected_is_an_intersecting_ready_filter(qapp) -> None:
    _, proxy = _proxy(
        [
            _document("auto"),
            _document("corrected", was_manually_corrected=True),
            _document("approved-corrected", "approved", was_manually_corrected=True),
        ]
    )
    proxy.set_route(QueueRoute.READY)
    proxy.set_ready_segment(ReadySegment.READY_TO_APPROVE)
    proxy.set_manually_corrected_only(True)

    assert _visible_ids(proxy) == ["corrected"]


@pytest.mark.parametrize(
    "segment, expected",
    [
        (AttentionSegment.ALL, ["review", "overlap", "failed", "skipped", "duplicate"]),
        (AttentionSegment.NEEDS_REVIEW, ["review", "overlap"]),
        (AttentionSegment.FAILED, ["failed"]),
        (AttentionSegment.SKIPPED, ["skipped"]),
        (AttentionSegment.SUSPECTED_DUPLICATE, ["overlap", "duplicate"]),
    ],
)
def test_attention_segments_allow_overlap(qapp, segment, expected) -> None:
    _, proxy = _proxy(
        [
            _document("review", "needs_review"),
            _document("overlap", "needs_review", is_duplicate_suspected=True),
            _document("failed", "failed"),
            _document("skipped", "skipped"),
            _document("duplicate", "approved", is_duplicate_suspected=True),
            _document("ready", "processed"),
        ]
    )
    proxy.set_route(QueueRoute.ATTENTION)
    proxy.set_attention_segment(segment)

    assert _visible_ids(proxy) == expected


def test_duplicate_only_filter_can_intersect_other_filters(qapp) -> None:
    _, proxy = _proxy(
        [
            _document("overlap", "needs_review", is_duplicate_suspected=True),
            _document("plain", "needs_review"),
        ]
    )
    proxy.set_route(QueueRoute.ATTENTION)
    proxy.set_attention_segment(AttentionSegment.NEEDS_REVIEW)
    proxy.set_suspected_duplicate_only(True)

    assert _visible_ids(proxy) == ["overlap"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("tax-invoice", ["file"]),
        ("ספק ירושלים", ["hebrew"]),
        ("globex", ["english"]),
        ("inv-404", ["number"]),
        ("GLOBEX", ["english"]),
        ("does-not-exist", []),
    ],
)
def test_search_scope_is_filename_supplier_and_document_number(qapp, query, expected) -> None:
    _, proxy = _proxy(
        [
            _document("file", file_name="Tax-Invoice-August.pdf", supplier_name=None),
            _document("hebrew", supplier_name="ספק ירושלים", invoice_number=None),
            _document("english", supplier_name="Globex LTD"),
            _document("number", invoice_number="INV-404"),
            _document("missing", supplier_name=None, invoice_number=None, file_name="blank.pdf"),
        ]
    )

    proxy.set_search_query(query)

    assert _visible_ids(proxy) == expected


def test_search_does_not_include_date_amount_or_folder(qapp) -> None:
    _, proxy = _proxy(
        [_document("one", folder_path="SecretFolder", invoice_date="23/08/2026", total=999)]
    )

    for query in ("SecretFolder", "23/08/2026", "999"):
        proxy.set_search_query(query)
        assert proxy.rowCount() == 0


@pytest.mark.parametrize(
    "column, documents, expected",
    [
        (
            DocumentColumn.TOTAL,
            [_document("high", total=1000), _document("low", total=9.5), _document("mid", total=80)],
            ["low", "mid", "high"],
        ),
        (
            DocumentColumn.CONFIDENCE,
            [
                _document("high", confidence=0.95),
                _document("low", confidence=0.2),
                _document("mid", confidence=0.75),
            ],
            ["low", "mid", "high"],
        ),
        (
            DocumentColumn.DATE,
            [
                _document("late", invoice_date="01/12/2026"),
                _document("early", invoice_date="31/01/2025"),
                _document("mid", invoice_date="15/02/2026"),
            ],
            ["early", "mid", "late"],
        ),
        (
            DocumentColumn.SUPPLIER,
            [
                _document("z", supplier_name="zebra"),
                _document("a", supplier_name="Alpha"),
                _document("b", supplier_name="beta"),
            ],
            ["a", "b", "z"],
        ),
    ],
)
def test_typed_sorting(qapp, column, documents, expected) -> None:
    model, proxy = _proxy(documents)

    proxy.sort(model.column_for(column), Qt.SortOrder.AscendingOrder)

    assert _visible_ids(proxy) == expected


def test_missing_typed_values_sort_as_a_stable_low_value(qapp) -> None:
    model, proxy = _proxy(
        [_document("known", total=10), _document("missing-b", total=None), _document("missing-a", total=None)]
    )

    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.AscendingOrder)
    assert _visible_ids(proxy) == ["missing-a", "missing-b", "known"]

    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.DescendingOrder)
    assert _visible_ids(proxy) == ["known", "missing-b", "missing-a"]


def test_proxy_source_mapping_resolves_stable_id_after_sort(qapp) -> None:
    model, proxy = _proxy([_document("large", total=500), _document("small", total=2)])
    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.AscendingOrder)

    proxy_index = proxy.index_for_document_id("large")

    assert proxy_index.row() == 1
    assert proxy.document_id_for_index(proxy_index) == "large"
    assert model.document_id_at(proxy.mapToSource(proxy_index).row()) == "large"


def test_update_does_not_change_identity_or_break_sorted_mapping(qapp) -> None:
    model, proxy = _proxy([_document("one", total=10), _document("two", total=20)])
    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.AscendingOrder)

    model.update_document(_document("one", total=30))

    assert _visible_ids(proxy) == ["two", "one"]
    assert proxy.index_for_document_id("one").isValid()


def test_filtering_hides_and_later_resolves_same_stable_id(qapp) -> None:
    _, proxy = _proxy([_document("one", supplier_name="Acme")])

    proxy.set_search_query("no match")
    assert not proxy.index_for_document_id("one").isValid()

    proxy.set_search_query("")
    assert proxy.index_for_document_id("one").isValid()


def test_selection_helpers_round_trip_ids_across_sort_and_restore(qapp) -> None:
    model, proxy = _proxy(
        [_document("one", total=30), _document("two", total=10), _document("three", total=20)]
    )
    selection = QItemSelectionModel(proxy)
    restore_selected_document_ids(selection, ["one", "three"], current_document_id="three")

    assert selected_document_ids(selection) == ["one", "three"]
    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.AscendingOrder)
    saved = selected_document_ids(selection)
    restored = restore_selected_document_ids(selection, saved, current_document_id="three")

    assert set(restored) == {"one", "three"}
    assert set(selected_document_ids(selection)) == {"one", "three"}
    assert proxy.document_id_for_index(selection.currentIndex()) == "three"


def test_restore_selection_skips_ids_hidden_by_filter(qapp) -> None:
    _, proxy = _proxy([_document("visible", supplier_name="Keep"), _document("hidden", supplier_name="Drop")])
    proxy.set_search_query("Keep")
    selection = QItemSelectionModel(proxy)

    restored = restore_selected_document_ids(selection, ["hidden", "visible"])

    assert restored == ["visible"]
    assert selected_document_ids(selection) == ["visible"]


def test_clear_filters_restores_complete_source_without_rebuilding(qapp) -> None:
    model, proxy = _proxy([_document("one"), _document("two", "failed")])
    proxy.set_route(QueueRoute.ATTENTION)
    proxy.set_search_query("two")
    assert proxy.rowCount() == 1

    proxy.clear_filters()

    assert proxy.sourceModel() is model
    assert proxy.rowCount() == 2


def test_thousand_record_model_filter_search_and_sort_sanity(qapp) -> None:
    documents = [
        _document(
            f"doc-{index:04d}",
            "needs_review" if index % 5 == 0 else "processed",
            supplier_name="ספק מיוחד" if index % 17 == 0 else f"Supplier {index}",
            total=index * 1.25,
            confidence=(index % 100) / 100,
            invoice_date=f"{(index % 28) + 1:02d}/{(index % 12) + 1:02d}/2026",
        )
        for index in range(1000)
    ]
    started = perf_counter()
    model, proxy = _proxy(documents)
    proxy.set_route(QueueRoute.READY)
    ready_count = proxy.rowCount()
    proxy.set_search_query("Supplier 999")
    search_count = proxy.rowCount()
    proxy.set_search_query("")
    proxy.sort(model.column_for(DocumentColumn.TOTAL), Qt.SortOrder.DescendingOrder)
    first_id = proxy.document_id_for_index(proxy.index(0, 0))
    elapsed = perf_counter() - started

    print(f"Panda queue sanity: 1000 records in {elapsed:.4f}s")
    assert ready_count == 800
    assert search_count == 1
    assert first_id == "doc-0999"
    assert elapsed < 5.0
