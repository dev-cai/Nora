"""Decision & Reporting 领域对象。"""

from .company_assessment import CompanyAssessment, CompanyAssessmentStatus
from .decision_case import DecisionCase, DecisionCaseStatus
from .job_fit import (
    JobFitAnalysis,
    JobFitCitation,
    JobFitCitationSource,
    JobFitInsight,
    JobFitLevel,
)
from .report import (
    DecisionReport,
    MatchSummary,
    ReportCitation,
    ReportFact,
    ReportRecommendation,
    ReportRuleResult,
    ReportSection,
    ReportUnknown,
)
from .rules import (
    RULE_SET_VERSION,
    RuleInputReference,
    RuleInputSource,
    RuleResult,
    RuleSetEvaluation,
    RuleStatus,
    evaluate_decision_rules,
)

__all__ = (
    "RULE_SET_VERSION",
    "CompanyAssessment",
    "CompanyAssessmentStatus",
    "DecisionCase",
    "DecisionCaseStatus",
    "JobFitAnalysis",
    "JobFitCitation",
    "JobFitCitationSource",
    "JobFitInsight",
    "JobFitLevel",
    "DecisionReport",
    "MatchSummary",
    "ReportCitation",
    "ReportFact",
    "ReportRecommendation",
    "ReportRuleResult",
    "ReportSection",
    "ReportUnknown",
    "RuleInputReference",
    "RuleInputSource",
    "RuleResult",
    "RuleSetEvaluation",
    "RuleStatus",
    "evaluate_decision_rules",
)
