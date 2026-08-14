import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
FORBIDDEN_DOMAIN_IMPORTS = {"fastapi", "httpx", "sqlalchemy", "asyncpg"}
FORBIDDEN_APPLICATION_IMPORTS = {"app.infrastructure", "sqlalchemy", "asyncpg"}


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for source_file in path.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules


def forbidden_imports(path: Path, forbidden: set[str]) -> set[str]:
    return {
        module
        for module in imported_modules(path)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden)
    }


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


def test_domain_does_not_import_external_frameworks() -> None:
    domain_path = ROOT / "app" / "domain"
    assert domain_path.is_dir()
    assert not forbidden_imports(domain_path, FORBIDDEN_DOMAIN_IMPORTS)


def test_application_does_not_import_infrastructure_or_database_frameworks() -> None:
    application_path = ROOT / "app" / "application"
    assert application_path.is_dir()
    assert not forbidden_imports(application_path, FORBIDDEN_APPLICATION_IMPORTS)


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


def test_forbidden_imports_detects_exact_and_nested_modules(tmp_path: Path) -> None:
    source_path = tmp_path / "layer"
    source_path.mkdir()
    (source_path / "invalid.py").write_text(
        "import sqlalchemy\nfrom app.infrastructure.database import Base\n",
        encoding="utf-8",
    )

    assert forbidden_imports(source_path, FORBIDDEN_APPLICATION_IMPORTS) == {
        "app.infrastructure.database",
        "sqlalchemy",
    }
