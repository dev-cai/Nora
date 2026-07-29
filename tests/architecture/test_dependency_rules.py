import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
FORBIDDEN_DOMAIN_IMPORTS = {"fastapi", "httpx", "sqlalchemy", "asyncpg"}


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for source_file in path.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_domain_does_not_import_external_frameworks() -> None:
    domain_imports = imported_roots(ROOT / "src" / "nora" / "domain")
    assert not domain_imports & FORBIDDEN_DOMAIN_IMPORTS
