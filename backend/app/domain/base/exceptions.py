"""Nora 领域异常及稳定错误码。"""

from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Mapping


class ErrorCode(StrEnum):
    """系统边界使用的完整稳定错误码。"""

    APPLICATION_DECISION_CONFLICT = "application_decision_conflict"
    APPLICATION_DECISION_KEY_TAKEN = "application_decision_key_taken"
    APPLICATION_DECISION_PERSISTENCE_FAILED = "application_decision_persistence_failed"
    APPLICATION_RECORD_KEY_TAKEN = "application_record_key_taken"
    APPLICATION_RECORD_PERSISTENCE_FAILED = "application_record_persistence_failed"
    APPLICATION_RECORD_TRANSITION_CONFLICT = "application_record_transition_conflict"
    APPLICATION_RECORD_VERSION_CONFLICT = "application_record_version_conflict"
    APPLICATION_ERROR = "application_error"
    ARTIFACT_CONFLICT = "artifact_conflict"
    ARTIFACT_CORRUPT = "artifact_corrupt"
    ARTIFACT_DELETE_FAILED = "artifact_delete_failed"
    ARTIFACT_STATE_CONFLICT = "artifact_state_conflict"
    ARTIFACT_STORAGE_UNAVAILABLE = "artifact_storage_unavailable"
    ARTIFACT_TOO_LARGE = "artifact_too_large"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHENTICATION_RATE_LIMITED = "authentication_rate_limited"
    COMPANY_ASSESSMENT_CONFLICT = "company_assessment_conflict"
    COMPANY_ASSESSMENT_UNAVAILABLE = "company_assessment_unavailable"
    COMPANY_SNAPSHOT_VERSION_CONFLICT = "company_snapshot_version_conflict"
    CONTENT_TOO_LARGE = "content_too_large"
    DATABASE_UNAVAILABLE = "database_unavailable"
    DECISION_CASE_CONFLICT = "decision_case_conflict"
    DECISION_CASE_IMMUTABLE = "decision_case_immutable"
    DECISION_INPUT_CONFLICT = "decision_input_conflict"
    DECISION_INPUT_UNAVAILABLE = "decision_input_unavailable"
    DECISION_PERSISTENCE_FAILED = "decision_persistence_failed"
    DECISION_REPORT_GENERATION_CONFLICT = "decision_report_generation_conflict"
    DECISION_REPORT_VERSION_CONFLICT = "decision_report_version_conflict"
    DECISION_RULE_INPUT_MISMATCH = "decision_rule_input_mismatch"
    DECODE_FAILED = "decode_failed"
    DOMAIN_ERROR = "domain_error"
    EMAIL_CONFLICT = "email_conflict"
    EMPTY_CONTENT = "empty_content"
    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_NOT_PERSISTED = "entity_not_persisted"
    FETCH_FAILED = "fetch_failed"
    FETCH_TIMEOUT = "fetch_timeout"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDEMPOTENCY_KEY_TAKEN = "idempotency_key_taken"
    IDENTITY_PERSISTENCE_FAILED = "identity_persistence_failed"
    IMAGE_TOO_LARGE = "image_too_large"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    INTERNAL_ERROR = "internal_error"
    INVALID_APPLICATION_DECISION_FINGERPRINT = "invalid_application_decision_fingerprint"
    INVALID_APPLICATION_DECISION_STATUS = "invalid_application_decision_status"
    INVALID_APPLICATION_RECORD = "invalid_application_record"
    INVALID_APPLICATION_RECORD_STATUS = "invalid_application_record_status"
    INVALID_ARTIFACT_CONTENT_TYPE = "invalid_artifact_content_type"
    INVALID_ARTIFACT_SHA256 = "invalid_artifact_sha256"
    INVALID_ARTIFACT_SIZE = "invalid_artifact_size"
    INVALID_AUDIT_ACTION = "invalid_audit_action"
    INVALID_AUDIT_IDEMPOTENCY_KEY = "invalid_audit_idempotency_key"
    INVALID_AUDIT_SUMMARY = "invalid_audit_summary"
    INVALID_AUDIT_TARGET_TYPE = "invalid_audit_target_type"
    INVALID_AUDIT_TARGET_VERSION = "invalid_audit_target_version"
    INVALID_COMPANY_ASSESSMENT_STATUS = "invalid_company_assessment_status"
    INVALID_COMPANY_FACT_STATUS = "invalid_company_fact_status"
    INVALID_COMPANY_NAME = "invalid_company_name"
    INVALID_COMPANY_TEXT = "invalid_company_text"
    INVALID_CONFIRMATION_STATUS = "invalid_confirmation_status"
    INVALID_CONFIRMATION_TRANSITION = "invalid_confirmation_transition"
    INVALID_CORRELATION_ID = "invalid_correlation_id"
    INVALID_DECISION_CASE_STATE = "invalid_decision_case_state"
    INVALID_DECISION_REASON = "invalid_decision_reason"
    INVALID_DRAFT_TEXT = "invalid_draft_text"
    INVALID_EMAIL = "invalid_email"
    INVALID_FAILURE_CODE = "invalid_failure_code"
    INVALID_FAILURE_MESSAGE = "invalid_failure_message"
    INVALID_GENERATION_IDENTITY = "invalid_generation_identity"
    INVALID_GENERATOR_VERSION = "invalid_generator_version"
    INVALID_IDEMPOTENCY_KEY = "invalid_idempotency_key"
    INVALID_INPUT_FINGERPRINT = "invalid_input_fingerprint"
    INVALID_INPUT_KIND = "invalid_input_kind"
    INVALID_JD_TEXT = "invalid_jd_text"
    INVALID_JOB_TITLE = "invalid_job_title"
    INVALID_LOCATION = "invalid_location"
    INVALID_MESSAGE_DRAFT_FINGERPRINT = "invalid_message_draft_fingerprint"
    INVALID_MESSAGE_DRAFT_HASH = "invalid_message_draft_hash"
    INVALID_MESSAGE_DRAFT_REVISION = "invalid_message_draft_revision"
    INVALID_MESSAGE_DRAFT_SOURCE = "invalid_message_draft_source"
    INVALID_MESSAGE_DRAFT_STYLE = "invalid_message_draft_style"
    INVALID_OBJECT_KEY = "invalid_object_key"
    INVALID_PAGINATION = "invalid_pagination"
    INVALID_PASSWORD = "invalid_password"
    INVALID_PROFILE = "invalid_profile"
    INVALID_PROFILE_FIELD = "invalid_profile_field"
    INVALID_PROFILE_ITEM_ID = "invalid_profile_item_id"
    INVALID_PROFILE_VERSION = "invalid_profile_version"
    INVALID_REFERRAL_CONTEXT = "invalid_referral_context"
    INVALID_REPORT_CONTENT = "invalid_report_content"
    INVALID_REPORT_GENERATOR_VERSION = "invalid_report_generator_version"
    INVALID_REPORT_RULE_SET_VERSION = "invalid_report_rule_set_version"
    INVALID_REPORT_VERSION = "invalid_report_version"
    INVALID_REQUIREMENT = "invalid_requirement"
    INVALID_REQUIREMENT_FIELD = "invalid_requirement_field"
    INVALID_RESUME_CONTENT = "invalid_resume_content"
    INVALID_RESUME_PDF_INPUT = "invalid_resume_pdf_input"
    INVALID_RESUME_PDF_STATE = "invalid_resume_pdf_state"
    INVALID_RESUME_TITLE = "invalid_resume_title"
    INVALID_RESUME_VERSION = "invalid_resume_version"
    INVALID_RULE_SET_VERSION = "invalid_rule_set_version"
    INVALID_SOURCE_LOCATOR = "invalid_source_locator"
    INVALID_SOURCE_METADATA = "invalid_source_metadata"
    INVALID_SOURCE_RANGE = "invalid_source_range"
    INVALID_SOURCE_SHA256 = "invalid_source_sha256"
    INVALID_SOURCE_TYPE = "invalid_source_type"
    INVALID_SOURCE_URL = "invalid_source_url"
    INVALID_TEMPLATE_FIELD = "invalid_template_field"
    INVALID_TEMPLATE_SECTION = "invalid_template_section"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_URL = "invalid_url"
    INVALID_USERNAME = "invalid_username"
    INVALID_VARIANT_BLOCKS = "invalid_variant_blocks"
    INVALID_VARIANT_FIELD = "invalid_variant_field"
    INVALID_VARIANT_FINGERPRINT = "invalid_variant_fingerprint"
    INVALID_VARIANT_TEXT = "invalid_variant_text"
    INVALID_VERSION = "invalid_version"
    JD_TEXT_TOO_LONG = "jd_text_too_long"
    JOB_POSTING_PERSISTENCE_FAILED = "job_posting_persistence_failed"
    JOB_REQUIREMENT_VERSION_CONFLICT = "job_requirement_version_conflict"
    MESSAGE_DRAFT_CONFLICT = "message_draft_conflict"
    MESSAGE_DRAFT_INPUT_UNAVAILABLE = "message_draft_input_unavailable"
    MESSAGE_DRAFT_VERSION_CONFLICT = "message_draft_version_conflict"
    NORA_ERROR = "nora_error"
    OCR_FAILED = "ocr_failed"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    PDF_GENERATION_FAILED = "pdf_generation_failed"
    PDF_RENDER_FAILED = "pdf_render_failed"
    PROFILE_HAS_NO_CONFIRMED_DATA = "profile_has_no_confirmed_data"
    PROFILE_VERSION_CONFLICT = "profile_version_conflict"
    REFERRAL_CONTEXT_REQUIRED = "referral_context_required"
    REPORT_INPUT_MISMATCH = "report_input_mismatch"
    REQUIRED_VARIANT_FIELD = "required_variant_field"
    RESPONSE_TOO_LARGE = "response_too_large"
    RESUME_PDF_CONFLICT = "resume_pdf_conflict"
    RESUME_PDF_PERSISTENCE_FAILED = "resume_pdf_persistence_failed"
    RESUME_PDF_STATE_CONFLICT = "resume_pdf_state_conflict"
    RESUME_VARIANT_KEY_TAKEN = "resume_variant_key_taken"
    RESUME_VARIANT_PERSISTENCE_FAILED = "resume_variant_persistence_failed"
    RESUME_VERSION_CONFLICT = "resume_version_conflict"
    SKIP_REASON_REQUIRED = "skip_reason_required"
    SOURCE_CONFLICT = "source_conflict"
    TEMPLATE_DEFINITION_INVALID = "template_definition_invalid"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    UNSAFE_URL = "unsafe_url"
    UNSUPPORTED_ARTIFACT_TYPE = "unsupported_artifact_type"
    UNSUPPORTED_IMAGE = "unsupported_image"
    UNSUPPORTED_RULE_SET_VERSION = "unsupported_rule_set_version"
    USERNAME_CONFLICT = "username_conflict"
    VALIDATION_ERROR = "validation_error"
    VERSION_CONFLICT = "version_conflict"


class ErrorCategory(StrEnum):
    """协议适配器可映射的稳定错误类别。"""

    INVALID_INPUT = "invalid_input"
    AUTHENTICATION = "authentication"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    REQUEST_VALIDATION = "request_validation"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_FAILURE = "upstream_failure"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    INTERNAL = "internal"


def _category_map() -> dict[ErrorCode, ErrorCategory]:
    grouped: dict[ErrorCategory, tuple[ErrorCode, ...]] = {
        ErrorCategory.INVALID_INPUT: (
            ErrorCode.ARTIFACT_UNAVAILABLE,
            ErrorCode.CONTENT_TOO_LARGE,
            ErrorCode.DECISION_CASE_IMMUTABLE,
            ErrorCode.DECISION_RULE_INPUT_MISMATCH,
            ErrorCode.DECODE_FAILED,
            ErrorCode.EMPTY_CONTENT,
            ErrorCode.IMAGE_TOO_LARGE,
            ErrorCode.INVALID_APPLICATION_DECISION_FINGERPRINT,
            ErrorCode.INVALID_APPLICATION_DECISION_STATUS,
            ErrorCode.INVALID_APPLICATION_RECORD,
            ErrorCode.INVALID_APPLICATION_RECORD_STATUS,
            ErrorCode.INVALID_ARTIFACT_CONTENT_TYPE,
            ErrorCode.INVALID_ARTIFACT_SHA256,
            ErrorCode.INVALID_ARTIFACT_SIZE,
            ErrorCode.INVALID_AUDIT_ACTION,
            ErrorCode.INVALID_AUDIT_IDEMPOTENCY_KEY,
            ErrorCode.INVALID_AUDIT_SUMMARY,
            ErrorCode.INVALID_AUDIT_TARGET_TYPE,
            ErrorCode.INVALID_AUDIT_TARGET_VERSION,
            ErrorCode.INVALID_COMPANY_ASSESSMENT_STATUS,
            ErrorCode.INVALID_COMPANY_FACT_STATUS,
            ErrorCode.INVALID_COMPANY_NAME,
            ErrorCode.INVALID_COMPANY_TEXT,
            ErrorCode.INVALID_CONFIRMATION_STATUS,
            ErrorCode.INVALID_CONFIRMATION_TRANSITION,
            ErrorCode.INVALID_CORRELATION_ID,
            ErrorCode.INVALID_DECISION_CASE_STATE,
            ErrorCode.INVALID_DECISION_REASON,
            ErrorCode.INVALID_DRAFT_TEXT,
            ErrorCode.INVALID_EMAIL,
            ErrorCode.INVALID_FAILURE_CODE,
            ErrorCode.INVALID_FAILURE_MESSAGE,
            ErrorCode.INVALID_GENERATION_IDENTITY,
            ErrorCode.INVALID_GENERATOR_VERSION,
            ErrorCode.INVALID_IDEMPOTENCY_KEY,
            ErrorCode.INVALID_INPUT_FINGERPRINT,
            ErrorCode.INVALID_INPUT_KIND,
            ErrorCode.INVALID_JD_TEXT,
            ErrorCode.INVALID_JOB_TITLE,
            ErrorCode.INVALID_LOCATION,
            ErrorCode.INVALID_MESSAGE_DRAFT_FINGERPRINT,
            ErrorCode.INVALID_MESSAGE_DRAFT_HASH,
            ErrorCode.INVALID_MESSAGE_DRAFT_REVISION,
            ErrorCode.INVALID_MESSAGE_DRAFT_SOURCE,
            ErrorCode.INVALID_MESSAGE_DRAFT_STYLE,
            ErrorCode.INVALID_OBJECT_KEY,
            ErrorCode.INVALID_PAGINATION,
            ErrorCode.INVALID_PASSWORD,
            ErrorCode.INVALID_PROFILE,
            ErrorCode.INVALID_PROFILE_FIELD,
            ErrorCode.INVALID_PROFILE_ITEM_ID,
            ErrorCode.INVALID_PROFILE_VERSION,
            ErrorCode.INVALID_REFERRAL_CONTEXT,
            ErrorCode.INVALID_REPORT_CONTENT,
            ErrorCode.INVALID_REPORT_GENERATOR_VERSION,
            ErrorCode.INVALID_REPORT_RULE_SET_VERSION,
            ErrorCode.INVALID_REPORT_VERSION,
            ErrorCode.INVALID_REQUIREMENT,
            ErrorCode.INVALID_REQUIREMENT_FIELD,
            ErrorCode.INVALID_RESUME_CONTENT,
            ErrorCode.INVALID_RESUME_PDF_INPUT,
            ErrorCode.INVALID_RESUME_PDF_STATE,
            ErrorCode.INVALID_RESUME_TITLE,
            ErrorCode.INVALID_RESUME_VERSION,
            ErrorCode.INVALID_RULE_SET_VERSION,
            ErrorCode.INVALID_SOURCE_LOCATOR,
            ErrorCode.INVALID_SOURCE_METADATA,
            ErrorCode.INVALID_SOURCE_RANGE,
            ErrorCode.INVALID_SOURCE_SHA256,
            ErrorCode.INVALID_SOURCE_TYPE,
            ErrorCode.INVALID_SOURCE_URL,
            ErrorCode.INVALID_TEMPLATE_FIELD,
            ErrorCode.INVALID_TEMPLATE_SECTION,
            ErrorCode.INVALID_TIMESTAMP,
            ErrorCode.INVALID_URL,
            ErrorCode.INVALID_USERNAME,
            ErrorCode.INVALID_VARIANT_BLOCKS,
            ErrorCode.INVALID_VARIANT_FIELD,
            ErrorCode.INVALID_VARIANT_FINGERPRINT,
            ErrorCode.INVALID_VARIANT_TEXT,
            ErrorCode.INVALID_VERSION,
            ErrorCode.JD_TEXT_TOO_LONG,
            ErrorCode.PROFILE_HAS_NO_CONFIRMED_DATA,
            ErrorCode.REFERRAL_CONTEXT_REQUIRED,
            ErrorCode.REPORT_INPUT_MISMATCH,
            ErrorCode.REQUIRED_VARIANT_FIELD,
            ErrorCode.RESPONSE_TOO_LARGE,
            ErrorCode.RESUME_PDF_STATE_CONFLICT,
            ErrorCode.SKIP_REASON_REQUIRED,
            ErrorCode.TEMPLATE_DEFINITION_INVALID,
            ErrorCode.TOO_MANY_REDIRECTS,
            ErrorCode.UNSAFE_URL,
            ErrorCode.UNSUPPORTED_IMAGE,
        ),
        ErrorCategory.AUTHENTICATION: (ErrorCode.AUTHENTICATION_FAILED,),
        ErrorCategory.FORBIDDEN: (ErrorCode.ORIGIN_NOT_ALLOWED,),
        ErrorCategory.NOT_FOUND: (ErrorCode.ENTITY_NOT_FOUND,),
        ErrorCategory.CONFLICT: (
            ErrorCode.APPLICATION_DECISION_CONFLICT,
            ErrorCode.APPLICATION_DECISION_KEY_TAKEN,
            ErrorCode.APPLICATION_RECORD_KEY_TAKEN,
            ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT,
            ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT,
            ErrorCode.ARTIFACT_CONFLICT,
            ErrorCode.ARTIFACT_STATE_CONFLICT,
            ErrorCode.COMPANY_ASSESSMENT_CONFLICT,
            ErrorCode.COMPANY_SNAPSHOT_VERSION_CONFLICT,
            ErrorCode.DECISION_CASE_CONFLICT,
            ErrorCode.DECISION_INPUT_CONFLICT,
            ErrorCode.DECISION_REPORT_GENERATION_CONFLICT,
            ErrorCode.DECISION_REPORT_VERSION_CONFLICT,
            ErrorCode.EMAIL_CONFLICT,
            ErrorCode.IDEMPOTENCY_CONFLICT,
            ErrorCode.JOB_REQUIREMENT_VERSION_CONFLICT,
            ErrorCode.MESSAGE_DRAFT_CONFLICT,
            ErrorCode.MESSAGE_DRAFT_VERSION_CONFLICT,
            ErrorCode.PROFILE_VERSION_CONFLICT,
            ErrorCode.RESUME_PDF_CONFLICT,
            ErrorCode.RESUME_VARIANT_KEY_TAKEN,
            ErrorCode.RESUME_VERSION_CONFLICT,
            ErrorCode.SOURCE_CONFLICT,
            ErrorCode.UNSUPPORTED_RULE_SET_VERSION,
            ErrorCode.USERNAME_CONFLICT,
        ),
        ErrorCategory.PAYLOAD_TOO_LARGE: (ErrorCode.ARTIFACT_TOO_LARGE,),
        ErrorCategory.UNSUPPORTED_MEDIA_TYPE: (ErrorCode.UNSUPPORTED_ARTIFACT_TYPE,),
        ErrorCategory.REQUEST_VALIDATION: (ErrorCode.VALIDATION_ERROR,),
        ErrorCategory.RATE_LIMITED: (ErrorCode.AUTHENTICATION_RATE_LIMITED,),
        ErrorCategory.UPSTREAM_FAILURE: (ErrorCode.FETCH_FAILED, ErrorCode.OCR_FAILED),
        ErrorCategory.UPSTREAM_TIMEOUT: (ErrorCode.FETCH_TIMEOUT,),
        ErrorCategory.SERVICE_UNAVAILABLE: (
            ErrorCode.APPLICATION_DECISION_PERSISTENCE_FAILED,
            ErrorCode.APPLICATION_RECORD_PERSISTENCE_FAILED,
            ErrorCode.ARTIFACT_CORRUPT,
            ErrorCode.ARTIFACT_DELETE_FAILED,
            ErrorCode.ARTIFACT_STORAGE_UNAVAILABLE,
            ErrorCode.COMPANY_ASSESSMENT_UNAVAILABLE,
            ErrorCode.DATABASE_UNAVAILABLE,
            ErrorCode.DECISION_INPUT_UNAVAILABLE,
            ErrorCode.DECISION_PERSISTENCE_FAILED,
            ErrorCode.IDENTITY_PERSISTENCE_FAILED,
            ErrorCode.JOB_POSTING_PERSISTENCE_FAILED,
            ErrorCode.MESSAGE_DRAFT_INPUT_UNAVAILABLE,
            ErrorCode.PDF_GENERATION_FAILED,
            ErrorCode.PDF_RENDER_FAILED,
            ErrorCode.RESUME_PDF_PERSISTENCE_FAILED,
            ErrorCode.RESUME_VARIANT_PERSISTENCE_FAILED,
        ),
        ErrorCategory.INTERNAL: (
            ErrorCode.APPLICATION_ERROR,
            ErrorCode.DOMAIN_ERROR,
            ErrorCode.ENTITY_NOT_PERSISTED,
            ErrorCode.IDEMPOTENCY_KEY_TAKEN,
            ErrorCode.INFRASTRUCTURE_ERROR,
            ErrorCode.INTERNAL_ERROR,
            ErrorCode.NORA_ERROR,
            ErrorCode.VERSION_CONFLICT,
        ),
    }
    registry: dict[ErrorCode, ErrorCategory] = {}
    for category, codes in grouped.items():
        for code in codes:
            if code in registry:
                raise RuntimeError(f"Duplicate ErrorCode category: {code}")
            registry[code] = category
    if set(registry) != set(ErrorCode):
        raise RuntimeError("Every ErrorCode must have exactly one category")
    return registry


ERROR_CATEGORY_BY_CODE: Final[Mapping[ErrorCode, ErrorCategory]] = MappingProxyType(_category_map())


class NoraError(Exception):
    """所有可预期 Nora 错误的基类。"""

    default_error_code = ErrorCode.NORA_ERROR

    def __init__(self, message: str, error_code: ErrorCode | None = None) -> None:
        if error_code is not None and not isinstance(error_code, ErrorCode):
            raise TypeError("error_code must be an ErrorCode")
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.default_error_code

    def to_dict(self) -> dict[str, Any]:
        """返回协议无关的稳定错误信息。"""

        return {"error_code": self.error_code, "message": self.message}


class DomainError(NoraError):
    """领域规则或领域状态不满足时抛出的错误。"""

    default_error_code = ErrorCode.DOMAIN_ERROR


class ApplicationError(NoraError):
    """应用用例无法完成时抛出的错误。"""

    default_error_code = ErrorCode.APPLICATION_ERROR


class InfrastructureError(NoraError):
    """基础设施适配器失败时抛出的错误。"""

    default_error_code = ErrorCode.INFRASTRUCTURE_ERROR


class RateLimitError(NoraError):
    """Stable rate-limit failure carrying only an integer retry delay."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message, error_code=ErrorCode.AUTHENTICATION_RATE_LIMITED)
        self.retry_after = max(1, int(retry_after))
