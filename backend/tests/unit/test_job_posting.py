"""岗位快照领域规则单元测试。"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.domain.base.exceptions import DomainError
from app.domain.opportunity import JobPosting, JobPostingStatus, JobSourceType
from app.domain.opportunity.job_posting import MAX_JD_TEXT_LENGTH, SUMMARY_MAX_LENGTH


def test_job_posting_normalizes_fields_and_builds_summary() -> None:
    now = datetime(2026, 7, 29, 8, 30, tzinfo=timezone.utc)
    owner_id = uuid4()
    posting = JobPosting.create(
        owner_id=owner_id,
        jd_text="  Senior Python Engineer\r\n\r\nBuild reliable APIs.  ",
        job_title="  Senior   Python Engineer ",
        company_name=" Example   Corp ",
        location=" Shanghai ",
        source_type=JobSourceType.URL,
        source_url=" https://jobs.example.com/roles/123 ",
        now=now,
    )

    assert posting.owner_id == owner_id
    assert posting.jd_text == "Senior Python Engineer\n\nBuild reliable APIs."
    assert posting.job_title == "Senior Python Engineer"
    assert posting.company_name == "Example Corp"
    assert posting.location == "Shanghai"
    assert posting.source_url == "https://jobs.example.com/roles/123"
    assert posting.text_summary == "Senior Python Engineer Build reliable APIs."
    assert posting.status is JobPostingStatus.ACTIVE
    assert posting.imported_at == now
    assert posting.created_at == now
    with pytest.raises(FrozenInstanceError):
        setattr(posting, "status", JobPostingStatus.ARCHIVED)


def test_job_posting_summary_has_a_stable_maximum_length() -> None:
    posting = JobPosting.create(owner_id=uuid4(), jd_text="word " * 100)

    assert len(posting.text_summary) <= SUMMARY_MAX_LENGTH
    assert posting.text_summary.endswith("...")


@pytest.mark.parametrize("jd_text", ["", "  \r\n  "])
def test_job_posting_rejects_blank_text(jd_text: str) -> None:
    with pytest.raises(DomainError) as error:
        JobPosting.create(owner_id=uuid4(), jd_text=jd_text)

    assert error.value.error_code == "invalid_jd_text"


def test_job_posting_rejects_oversized_text() -> None:
    with pytest.raises(DomainError) as error:
        JobPosting.create(owner_id=uuid4(), jd_text="x" * (MAX_JD_TEXT_LENGTH + 1))

    assert error.value.error_code == "jd_text_too_long"


@pytest.mark.parametrize(
    "source_url",
    [
        "ftp://jobs.example.com/123",
        "https://user:password@jobs.example.com/123",
        "https://jobs.example.com/a path",
        "not-a-url",
    ],
)
def test_job_posting_rejects_invalid_source_url(source_url: str) -> None:
    with pytest.raises(DomainError) as error:
        JobPosting.create(owner_id=uuid4(), jd_text="JD", source_url=source_url)

    assert error.value.error_code == "invalid_source_url"


def test_url_source_requires_source_url() -> None:
    with pytest.raises(DomainError) as error:
        JobPosting.create(owner_id=uuid4(), jd_text="JD", source_type=JobSourceType.URL)

    assert error.value.error_code == "invalid_source_url"


def test_job_posting_rejects_naive_timestamp() -> None:
    with pytest.raises(DomainError) as error:
        JobPosting.create(
            owner_id=uuid4(),
            jd_text="JD",
            now=datetime(2026, 7, 29, 8, 30),
        )

    assert error.value.error_code == "invalid_timestamp"
