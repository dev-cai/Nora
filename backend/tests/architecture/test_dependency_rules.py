import ast
from dataclasses import dataclass
from pathlib import Path
from sys import stdlib_module_names

import pytest

ROOT = Path(__file__).parents[2]


@dataclass(frozen=True, slots=True)
class ImportReference:
    source_path: Path
    source_module: str
    imported_module: str
    line: int


@dataclass(frozen=True, slots=True)
class LayerRule:
    name: str
    relative_path: Path
    allowed_app_prefixes: frozenset[str]
    standard_library_only: bool


LAYER_RULES = (
    LayerRule(
        name="domain",
        relative_path=Path("app/domain"),
        allowed_app_prefixes=frozenset({"app.domain"}),
        standard_library_only=True,
    ),
    LayerRule(
        name="ports",
        relative_path=Path("app/ports"),
        allowed_app_prefixes=frozenset({"app.domain", "app.ports"}),
        standard_library_only=True,
    ),
    LayerRule(
        name="application",
        relative_path=Path("app/application"),
        allowed_app_prefixes=frozenset({"app.application", "app.domain", "app.ports"}),
        standard_library_only=True,
    ),
    LayerRule(
        name="infrastructure",
        relative_path=Path("app/infrastructure"),
        allowed_app_prefixes=frozenset({"app.domain", "app.infrastructure", "app.ports"}),
        standard_library_only=False,
    ),
    LayerRule(
        name="apps",
        relative_path=Path("app/apps"),
        allowed_app_prefixes=frozenset(
            {
                "app.application",
                "app.apps",
                "app.domain",
                "app.infrastructure",
                "app.ports",
            }
        ),
        standard_library_only=False,
    ),
)
RULES_BY_NAME = {rule.name: rule for rule in LAYER_RULES}

FORBIDDEN_FRAMEWORK_IMPORTS = {
    "domain": frozenset({"asyncpg", "fastapi", "httpx", "langgraph", "pydantic", "sqlalchemy"}),
    "ports": frozenset({"asyncpg", "fastapi", "httpx", "langgraph", "pydantic", "sqlalchemy"}),
    "application": frozenset({"asyncpg", "fastapi", "langgraph", "pydantic", "sqlalchemy"}),
    "infrastructure": frozenset({"fastapi"}),
}

BOUNDED_CONTEXTS = frozenset(
    {"career", "decision", "followup", "governance", "identity", "knowledge", "opportunity"}
)
FLAT_INFRASTRUCTURE_CONTEXTS = {
    "app.infrastructure.auth": "identity",
    "app.infrastructure.jd_fetch": "opportunity",
    "app.infrastructure.jd_ocr": "opportunity",
    "app.infrastructure.object_storage": "knowledge",
    "app.infrastructure.pdf_renderer": "followup",
}
CROSS_CONTEXT_INFRASTRUCTURE_EXCEPTIONS = {
    (
        "app.infrastructure.database.career",
        "app.infrastructure.database.identity",
    ): "CandidateProfile and ResumeVersion lock the owning UserRecord row.",
    (
        "app.infrastructure.database.opportunity",
        "app.infrastructure.database.identity",
    ): "JobPosting and CompanySnapshot use the shared owner record and owner lock.",
}


def _module_name(source_file: Path, root: Path) -> str:
    parts = list(source_file.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_from_import(
    node: ast.ImportFrom,
    source_module: str,
    root: Path,
    *,
    source_is_package: bool,
) -> tuple[str, ...]:
    if node.level == 0:
        base_module = node.module
    else:
        package = source_module.split(".") if source_is_package else source_module.split(".")[:-1]
        ascend = node.level - 1
        if ascend > len(package):
            return ()
        base = package[: len(package) - ascend]
        if node.module:
            base_module = ".".join([*base, *node.module.split(".")])
        else:
            return tuple(".".join([*base, alias.name]) for alias in node.names if alias.name != "*")

    if base_module is None:
        return ()
    existing_submodules = tuple(
        candidate
        for alias in node.names
        if alias.name != "*"
        if _module_exists(candidate := f"{base_module}.{alias.name}", root)
    )
    return (base_module, *existing_submodules)


def _module_exists(module: str, root: Path) -> bool:
    module_path = root.joinpath(*module.split("."))
    return module_path.with_suffix(".py").is_file() or (module_path / "__init__.py").is_file()


def import_references(path: Path, root: Path) -> tuple[ImportReference, ...]:
    references: list[ImportReference] = []
    for source_file in sorted(path.rglob("*.py")):
        source_module = _module_name(source_file, root)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = _resolve_from_import(
                    node,
                    source_module,
                    root,
                    source_is_package=source_file.name == "__init__.py",
                )
            else:
                continue
            references.extend(
                ImportReference(source_file, source_module, module, node.lineno)
                for module in modules
            )
    return tuple(references)


def _matches_prefix(module: str, prefixes: frozenset[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def package_dependency_violations(root: Path, rule: LayerRule) -> set[str]:
    violations: set[str] = set()
    layer_path = root / rule.relative_path
    for reference in import_references(layer_path, root):
        imported_root = reference.imported_module.partition(".")[0]
        if imported_root == "app":
            allowed = _matches_prefix(reference.imported_module, rule.allowed_app_prefixes)
        else:
            allowed = not rule.standard_library_only or imported_root in stdlib_module_names
        if not allowed:
            relative_source = reference.source_path.relative_to(root)
            violations.add(
                f"{relative_source}:{reference.line} imports {reference.imported_module}"
            )
    return violations


def forbidden_imports(root: Path, rule: LayerRule) -> set[str]:
    forbidden = FORBIDDEN_FRAMEWORK_IMPORTS.get(rule.name, frozenset())
    return {
        reference.imported_module
        for reference in import_references(root / rule.relative_path, root)
        if _matches_prefix(reference.imported_module, forbidden)
    }


def _infrastructure_context(module: str) -> str | None:
    database_prefix = "app.infrastructure.database."
    if module.startswith(database_prefix):
        context = module.removeprefix(database_prefix).partition(".")[0]
        return context if context in BOUNDED_CONTEXTS else None
    infrastructure_prefix = "app.infrastructure."
    if module.startswith(infrastructure_prefix):
        context = module.removeprefix(infrastructure_prefix).partition(".")[0]
        if context in BOUNDED_CONTEXTS:
            return context
    for prefix, context in FLAT_INFRASTRUCTURE_CONTEXTS.items():
        if module == prefix or module.startswith(f"{prefix}."):
            return context
    return None


def cross_context_infrastructure_edges(root: Path) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for reference in import_references(root / "app" / "infrastructure", root):
        source_context = _infrastructure_context(reference.source_module)
        target_context = _infrastructure_context(reference.imported_module)
        if source_context and target_context and source_context != target_context:
            edges.add((reference.source_module, reference.imported_module))
    return edges


def class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            }
    raise AssertionError(f"{class_name} not found in {path}")


@pytest.mark.parametrize("rule", LAYER_RULES, ids=lambda rule: rule.name)
def test_package_dependency_rule_accepts_current_tree(rule: LayerRule) -> None:
    assert (ROOT / rule.relative_path).is_dir()
    assert not package_dependency_violations(ROOT, rule)
    assert not forbidden_imports(ROOT, rule)


@pytest.mark.parametrize(
    ("rule_name", "invalid_import"),
    [
        ("ports", "from app.infrastructure.auth import JwtTokenIssuer\n"),
        ("application", "from app.apps.api import create_app\n"),
        ("infrastructure", "from app.application.career import CandidateProfileService\n"),
        ("apps", "from app.shared import UnsupportedSharedType\n"),
    ],
)
def test_package_dependency_rules_reject_forbidden_edges(
    tmp_path: Path, rule_name: str, invalid_import: str
) -> None:
    rule = RULES_BY_NAME[rule_name]
    source_path = tmp_path / rule.relative_path / "invalid.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(invalid_import, encoding="utf-8")

    violations = package_dependency_violations(tmp_path, rule)

    assert len(violations) == 1
    assert invalid_import.split()[1] in next(iter(violations))


def test_domain_rule_rejects_outer_layer_and_third_party(tmp_path: Path) -> None:
    rule = RULES_BY_NAME["domain"]
    source_path = tmp_path / rule.relative_path / "invalid.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from app.application.identity import IdentityService\nimport pendulum\n",
        encoding="utf-8",
    )

    violations = package_dependency_violations(tmp_path, rule)

    assert len(violations) == 2
    assert any("app.application.identity" in violation for violation in violations)
    assert any("pendulum" in violation for violation in violations)


def test_framework_blacklists_remain_explicit_supplementary_guards(tmp_path: Path) -> None:
    rule = RULES_BY_NAME["application"]
    source_path = tmp_path / rule.relative_path / "invalid.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "import sqlalchemy\nfrom fastapi.responses import JSONResponse\n",
        encoding="utf-8",
    )

    assert forbidden_imports(tmp_path, rule) == {"fastapi.responses", "sqlalchemy"}


def test_cross_context_infrastructure_edges_are_explicit_and_minimal() -> None:
    edges = cross_context_infrastructure_edges(ROOT)
    exceptions = set(CROSS_CONTEXT_INFRASTRUCTURE_EXCEPTIONS)

    assert edges == exceptions
    assert all(reason.strip() for reason in CROSS_CONTEXT_INFRASTRUCTURE_EXCEPTIONS.values())


def test_cross_context_rule_resolves_relative_imports(tmp_path: Path) -> None:
    source_path = tmp_path / "app" / "infrastructure" / "database" / "decision.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from .career import CandidateProfileRecord\n",
        encoding="utf-8",
    )

    assert cross_context_infrastructure_edges(tmp_path) == {
        (
            "app.infrastructure.database.decision",
            "app.infrastructure.database.career",
        )
    }


@pytest.mark.parametrize(
    ("source_module", "target_module", "source_import"),
    [
        (
            "app.infrastructure.database.decision",
            "app.infrastructure.database.identity",
            "from app.infrastructure.database import identity\n",
        ),
        (
            "app.infrastructure.database.career",
            "app.infrastructure.auth",
            "from app.infrastructure import auth\n",
        ),
    ],
)
def test_cross_context_rule_resolves_absolute_submodule_imports(
    tmp_path: Path,
    source_module: str,
    target_module: str,
    source_import: str,
) -> None:
    source_path = tmp_path.joinpath(*source_module.split(".")).with_suffix(".py")
    target_path = tmp_path.joinpath(*target_module.split(".")).with_suffix(".py")
    source_path.parent.mkdir(parents=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_import, encoding="utf-8")
    target_path.touch()

    assert cross_context_infrastructure_edges(tmp_path) == {(source_module, target_module)}


def test_reference_repositories_do_not_own_transaction_boundaries() -> None:
    ports_path = ROOT / "app" / "ports"

    assert class_method_names(ports_path / "transaction.py", "Transaction") == {
        "commit",
        "rollback",
    }
    for path, class_name in (
        (ports_path / "opportunity.py", "JobPostingRepository"),
        (ports_path / "followup.py", "ApplicationDecisionRepository"),
    ):
        assert class_method_names(path, class_name).isdisjoint({"commit", "rollback"})
