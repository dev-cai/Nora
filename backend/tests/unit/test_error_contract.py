"""Typed error registry, API mapping and migration guard tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from app.apps.api.errors import HTTP_STATUS_BY_CATEGORY, problem_from_error
from app.domain.base.exceptions import (
    ERROR_CATEGORY_BY_CODE,
    ErrorCategory,
    ErrorCode,
    NoraError,
)

EXPECTED_ERROR_CODES = frozenset(
    """
    application_decision_conflict application_decision_key_taken
    application_decision_persistence_failed application_record_key_taken
    application_record_persistence_failed application_record_transition_conflict
    application_record_version_conflict application_error artifact_conflict artifact_corrupt
    artifact_delete_failed artifact_state_conflict artifact_storage_unavailable artifact_too_large
    artifact_unavailable authentication_failed authentication_rate_limited
    company_assessment_conflict
    company_assessment_unavailable company_snapshot_version_conflict content_too_large
    database_unavailable decision_case_conflict decision_case_immutable decision_input_conflict
    decision_input_unavailable decision_persistence_failed decision_report_generation_conflict
    decision_report_version_conflict decision_rule_input_mismatch decode_failed domain_error
    email_conflict empty_content entity_not_found entity_not_persisted fetch_failed fetch_timeout
    idempotency_conflict idempotency_key_taken identity_persistence_failed image_too_large
    infrastructure_error internal_error invalid_application_decision_fingerprint
    invalid_application_decision_status invalid_application_record invalid_application_record_status
    invalid_artifact_content_type invalid_artifact_sha256
    invalid_artifact_size invalid_audit_action invalid_audit_idempotency_key invalid_audit_summary
    invalid_audit_target_type invalid_audit_target_version invalid_company_assessment_status
    invalid_company_fact_status invalid_company_name invalid_company_text
    invalid_confirmation_status
    invalid_confirmation_transition invalid_correlation_id invalid_decision_case_state
    invalid_decision_reason invalid_draft_text invalid_email invalid_failure_code
    invalid_failure_message invalid_generation_identity invalid_generator_version
    invalid_idempotency_key invalid_input_fingerprint invalid_input_kind invalid_jd_text
    invalid_job_title invalid_location invalid_message_draft_fingerprint invalid_message_draft_hash
    invalid_message_draft_revision invalid_message_draft_source invalid_message_draft_style
    invalid_object_key invalid_pagination invalid_password invalid_profile invalid_profile_field
    invalid_profile_item_id invalid_profile_version invalid_referral_context invalid_report_content
    invalid_report_generator_version invalid_report_rule_set_version invalid_report_version
    invalid_requirement invalid_requirement_field invalid_resume_content invalid_resume_pdf_input
    invalid_resume_pdf_state invalid_resume_title invalid_resume_version invalid_rule_set_version
    invalid_source_locator invalid_source_metadata invalid_source_range invalid_source_sha256
    invalid_source_type invalid_source_url invalid_template_field invalid_template_section
    invalid_timestamp invalid_url invalid_username invalid_variant_blocks invalid_variant_field
    invalid_variant_fingerprint invalid_variant_text invalid_version jd_text_too_long
    job_posting_persistence_failed job_requirement_version_conflict message_draft_conflict
    message_draft_input_unavailable message_draft_version_conflict nora_error ocr_failed
    origin_not_allowed
    pdf_generation_failed pdf_render_failed profile_has_no_confirmed_data profile_version_conflict
    referral_context_required report_input_mismatch required_variant_field response_too_large
    resume_pdf_conflict resume_pdf_persistence_failed resume_pdf_state_conflict
    resume_variant_key_taken resume_variant_persistence_failed resume_version_conflict
    skip_reason_required source_conflict template_definition_invalid too_many_redirects unsafe_url
    unsupported_artifact_type unsupported_image unsupported_rule_set_version username_conflict
    validation_error version_conflict
    """.split()
)


def test_error_code_registry_is_exact_complete_and_immutable() -> None:
    assert len(EXPECTED_ERROR_CODES) == 152
    assert {code.value for code in ErrorCode} == EXPECTED_ERROR_CODES
    assert set(ErrorCode) == set(ERROR_CATEGORY_BY_CODE)
    with pytest.raises(TypeError):
        ERROR_CATEGORY_BY_CODE[ErrorCode.INVALID_JD_TEXT] = ErrorCategory.INTERNAL  # type: ignore[index]


def test_all_error_categories_have_one_central_http_status() -> None:
    assert HTTP_STATUS_BY_CATEGORY == {
        ErrorCategory.INVALID_INPUT: 400,
        ErrorCategory.AUTHENTICATION: 401,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.PAYLOAD_TOO_LARGE: 413,
        ErrorCategory.UNSUPPORTED_MEDIA_TYPE: 415,
        ErrorCategory.REQUEST_VALIDATION: 422,
        ErrorCategory.RATE_LIMITED: 429,
        ErrorCategory.UPSTREAM_FAILURE: 502,
        ErrorCategory.SERVICE_UNAVAILABLE: 503,
        ErrorCategory.UPSTREAM_TIMEOUT: 504,
        ErrorCategory.INTERNAL: 500,
    }
    assert set(HTTP_STATUS_BY_CATEGORY) == set(ErrorCategory)


@pytest.mark.parametrize(
    "code",
    [
        ErrorCode.APPLICATION_ERROR,
        ErrorCode.DOMAIN_ERROR,
        ErrorCode.ENTITY_NOT_PERSISTED,
        ErrorCode.IDEMPOTENCY_KEY_TAKEN,
        ErrorCode.INFRASTRUCTURE_ERROR,
        ErrorCode.INTERNAL_ERROR,
        ErrorCode.NORA_ERROR,
        ErrorCode.VERSION_CONFLICT,
    ],
)
def test_internal_sentinels_fail_closed(code: ErrorCode) -> None:
    problem = problem_from_error(NoraError("sensitive details", code))
    assert problem.error_code is ErrorCode.INTERNAL_ERROR
    assert problem.error_category is ErrorCategory.INTERNAL
    assert problem.message == "Internal server error"


def test_production_code_uses_only_typed_error_codes() -> None:
    app_root = Path(__file__).parents[2] / "app"
    violations: list[str] = []
    for path in app_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "JdInputErrorCode" not in source
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "error_code"
                and any(isinstance(comparator, ast.Constant) for comparator in node.comparators)
            ):
                violations.append(f"{path.relative_to(app_root)}:{node.lineno}")
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "error_code" and isinstance(keyword.value, ast.Constant):
                    violations.append(f"{path.relative_to(app_root)}:{node.lineno}")
    assert violations == []
