"""RAG derived-data migration contract."""

from pathlib import Path


def test_rag_migration_declares_rebuildable_source_identity() -> None:
    migration = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0024_knowledge_chunks.py"
    ).read_text(encoding="utf-8")
    for marker in (
        '"knowledge_chunks"',
        "fk_chunk_source_owner",
        "uq_chunk_source_ordinal",
        "embedding_model",
        "embedding_version",
        "embedding_dimension",
    ):
        assert marker in migration
