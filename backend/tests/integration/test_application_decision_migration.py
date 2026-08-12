"""ApplicationDecision migration constraints."""

from pathlib import Path


def test_application_decision_migration_declares_fixed_version_constraints() -> None:
    migration = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "0013_application_decisions.py"
    ).read_text(encoding="utf-8")

    assert "uq_application_decision_owner_report" in migration
    assert "uq_application_decision_owner_key" in migration
    assert "fk_application_decision_report_owner" in migration
    assert "fk_application_decision_case_resume_owner" in migration
    assert "fk_application_decision_resume_owner" in migration
    assert "uq_decision_report_case_identity" in migration
    assert "uq_decision_case_resume_owner" in migration
    assert "ck_application_decision_actor_owner" in migration
    assert "ck_application_decision_skip_reason" in migration
