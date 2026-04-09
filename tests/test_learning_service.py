"""
Tests for app.services.learning_service.

Covers:
  - record_and_learn: no rule for address (already in base rules)
  - record_and_learn: rule created for date-like supplier
  - record_and_learn: rule created for phone number as supplier
  - record_and_learn: rule created for tax-ID as supplier
  - record_and_learn: literal rule after N repetitions
  - record_and_learn: no duplicate rule created
  - Learned rules integrate into supplier_validator.validate_supplier()
  - invalidate_rules_cache() causes reload from disk
"""

import json
import pytest
from pathlib import Path


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_data_paths(tmp_path, monkeypatch):
    """
    Redirect all data file paths to a temporary directory so tests do not
    touch real data files and do not interfere with each other.
    """
    import app.config as cfg
    import app.services.learning_service as ls
    import app.parsers.supplier_validator as sv

    monkeypatch.setattr(cfg, "CORRECTIONS_LOG_JSON", tmp_path / "corrections_log.json")
    monkeypatch.setattr(cfg, "LEARNED_RULES_JSON",   tmp_path / "learned_rules.json")
    monkeypatch.setattr(cfg, "SUPPLIER_RULES_JSON",  tmp_path / "supplier_rules.json")

    monkeypatch.setattr(ls, "CORRECTIONS_LOG_JSON", tmp_path / "corrections_log.json")
    monkeypatch.setattr(ls, "LEARNED_RULES_JSON",   tmp_path / "learned_rules.json")

    monkeypatch.setattr(sv, "SUPPLIER_RULES_JSON",  tmp_path / "supplier_rules.json")
    monkeypatch.setattr(sv, "LEARNED_RULES_JSON",   tmp_path / "learned_rules.json")

    # Always start with a clean cache between tests.
    sv.invalidate_rules_cache()
    yield
    sv.invalidate_rules_cache()


def _call(field, original, corrected="fixed value", fid="file1", fname="test.pdf"):
    from app.services.learning_service import record_and_learn
    return record_and_learn(field, original, corrected, fid, fname)


def _load_rules(tmp_path) -> list:
    p = tmp_path / "learned_rules.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("rules", [])


def _load_log(tmp_path) -> list:
    p = tmp_path / "corrections_log.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("corrections", [])


# ── Correction logging ────────────────────────────────────────────────────────

class TestCorrectionLogging:

    def test_correction_is_logged(self, tmp_path):
        _call("supplier_name", "some value")
        log = _load_log(tmp_path)
        assert len(log) == 1
        assert log[0]["field_name"]     == "supplier_name"
        assert log[0]["original_value"] == "some value"

    def test_no_change_is_not_logged(self, tmp_path):
        _call("supplier_name", "same", corrected="same")
        assert _load_log(tmp_path) == []

    def test_multiple_corrections_accumulate(self, tmp_path):
        _call("supplier_name", "value_a")
        _call("supplier_name", "value_b")
        assert len(_load_log(tmp_path)) == 2


# ── Rule inference: address ───────────────────────────────────────────────────

class TestAddressRule:

    def test_address_as_supplier_creates_no_rule(self, tmp_path):
        # Address is already caught by the base rule set — no duplicate needed.
        reason = _call("supplier_name", "דוד אלעזר 23, הרצליה")
        assert reason is None
        assert _load_rules(tmp_path) == []

    def test_address_is_still_logged(self, tmp_path):
        _call("supplier_name", "דוד אלעזר 23, הרצליה")
        assert len(_load_log(tmp_path)) == 1


# ── Rule inference: date-like ─────────────────────────────────────────────────

class TestDateLikeRule:

    def test_date_as_supplier_creates_rule_immediately(self, tmp_path):
        reason = _call("supplier_name", "31/01/2026")
        assert reason is not None
        rules = _load_rules(tmp_path)
        assert len(rules) == 1
        assert rules[0]["pattern_type"] == "date_like"
        assert rules[0]["field"]        == "supplier_name"

    def test_date_as_invoice_number_creates_rule(self, tmp_path):
        reason = _call("invoice_number", "31/01/2026")
        assert reason is not None
        rules = _load_rules(tmp_path)
        assert any(r["field"] == "invoice_number" and r["pattern_type"] == "date_like"
                   for r in rules)

    def test_date_rule_not_duplicated(self, tmp_path):
        _call("supplier_name", "01/02/2026")
        _call("supplier_name", "15/03/2026")   # different date, same pattern
        rules = _load_rules(tmp_path)
        date_rules = [r for r in rules if r["pattern_type"] == "date_like"
                      and r["field"] == "supplier_name"]
        assert len(date_rules) == 1   # only one rule for this pattern


# ── Rule inference: phone number ──────────────────────────────────────────────

class TestPhoneRule:

    def test_phone_as_supplier_creates_rule(self, tmp_path):
        reason = _call("supplier_name", "052-1234567")
        assert reason is not None
        rules = _load_rules(tmp_path)
        assert any(r["pattern_type"] == "phone_number" for r in rules)

    def test_phone_rule_not_duplicated(self, tmp_path):
        _call("supplier_name", "052-1234567")
        _call("supplier_name", "054-9876543")
        rules = [r for r in _load_rules(tmp_path) if r["pattern_type"] == "phone_number"]
        assert len(rules) == 1


# ── Rule inference: literal (repeated) ───────────────────────────────────────

class TestLiteralRule:

    def test_single_occurrence_creates_no_literal_rule(self, tmp_path):
        reason = _call("supplier_name", "מסמך ממוחשב")
        assert reason is None
        assert _load_rules(tmp_path) == []

    def test_two_occurrences_creates_no_literal_rule(self, tmp_path):
        _call("supplier_name", "מסמך ממוחשב", fid="f1")
        _call("supplier_name", "מסמך ממוחשב", fid="f2")
        assert _load_rules(tmp_path) == []

    def test_three_occurrences_creates_literal_rule(self, tmp_path):
        _call("supplier_name", "מסמך ממוחשב", fid="f1")
        _call("supplier_name", "מסמך ממוחשב", fid="f2")
        reason = _call("supplier_name", "מסמך ממוחשב", fid="f3")
        assert reason is not None
        rules = _load_rules(tmp_path)
        literal_rules = [r for r in rules if r["pattern_type"] == "literal"]
        assert len(literal_rules) == 1
        assert literal_rules[0]["value"] == "מסמך ממוחשב"

    def test_literal_rule_not_duplicated(self, tmp_path):
        for i in range(5):
            _call("supplier_name", "מסמך ממוחשב", fid=f"f{i}")
        literal_rules = [r for r in _load_rules(tmp_path) if r["pattern_type"] == "literal"]
        assert len(literal_rules) == 1


# ── Integration with supplier_validator ──────────────────────────────────────

class TestLearnedRulesIntegration:

    def _write_rule(self, tmp_path, rule: dict) -> None:
        path = tmp_path / "learned_rules.json"
        path.write_text(
            json.dumps({"version": 1, "rules": [rule]}, ensure_ascii=False),
            encoding="utf-8",
        )
        from app.parsers.supplier_validator import invalidate_rules_cache
        invalidate_rules_cache()

    def test_date_like_rule_rejects_date_supplier(self, tmp_path):
        self._write_rule(tmp_path, {
            "id": "lr_test_01", "field": "supplier_name",
            "action": "reject", "pattern_type": "date_like",
            "reason": "test",
        })
        from app.parsers.supplier_validator import validate_supplier
        result = validate_supplier("31/01/2026", "חשבון עסקה 1234\n31/01/2026\n")
        assert result.triggered_rule is not None
        assert "date_like" in result.triggered_rule

    def test_literal_rule_rejects_exact_value(self, tmp_path):
        self._write_rule(tmp_path, {
            "id": "lr_test_02", "field": "supplier_name",
            "action": "reject", "pattern_type": "literal",
            "value": "מסמך ממוחשב", "reason": "test",
        })
        from app.parsers.supplier_validator import validate_supplier
        result = validate_supplier("מסמך ממוחשב", "חשבון עסקה 1234\nמסמך ממוחשב\n")
        assert result.triggered_rule is not None
        assert "literal" in result.triggered_rule

    def test_unrelated_candidate_passes_learned_rules(self, tmp_path):
        self._write_rule(tmp_path, {
            "id": "lr_test_03", "field": "supplier_name",
            "action": "reject", "pattern_type": "date_like",
            "reason": "test",
        })
        from app.parsers.supplier_validator import validate_supplier
        result = validate_supplier('חברת בזק בינלאומי בע"מ', 'חברת בזק בינלאומי בע"מ\n')
        # A clean company name should NOT be rejected by the date_like rule.
        assert result.is_valid is True
        assert result.name is not None

    def test_invalidate_cache_causes_reload(self, tmp_path):
        from app.parsers.supplier_validator import validate_supplier, invalidate_rules_cache

        # First call — no learned rules.
        result1 = validate_supplier("31/01/2026", "")
        triggered_before = result1.triggered_rule

        # Write a date_like learned rule and invalidate cache.
        self._write_rule(tmp_path, {
            "id": "lr_test_04", "field": "supplier_name",
            "action": "reject", "pattern_type": "date_like",
            "reason": "test",
        })
        invalidate_rules_cache()

        # Second call — rule should now be applied.
        result2 = validate_supplier("31/01/2026", "")
        assert result2.triggered_rule != triggered_before
        assert result2.triggered_rule is not None
