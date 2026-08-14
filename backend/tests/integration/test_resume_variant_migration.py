"""ResumeVariant migration and seeded template contracts."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.domain.followup import TemplateDefinition
from app.infrastructure.database import TemplateDefinitionRecord
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_resume_variant_migration_round_trip_and_template_hashes(database_url: str) -> None:
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "0015_company_intelligence")
    command.upgrade(configuration, "0016_resume_variants")

    async def verify() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            records = list((await session.scalars(select(TemplateDefinitionRecord))).all())
        assert len(records) == 2
        for record in records:
            template = TemplateDefinition.create(
                template_id=record.template_id,
                version=record.version,
                name=record.name,
                page_size=record.definition["page_size"],
                density=record.definition["density"],
                accent=record.definition["accent"],
                section_order=tuple(record.definition["section_order"]),
                allowed_fields=tuple(record.definition["allowed_fields"]),
                required_fields=tuple(record.definition["required_fields"]),
                published_at=record.published_at,
            )
            assert template.definition_hash == record.definition_hash
        async with engine.begin() as connection:
            constraints = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'resume_variants'"
                )
            )
            names = {row[0] for row in constraints}
            assert "fk_resume_variant_apply_decision" in names
            assert "fk_resume_variant_template_input" in names
            assert "uq_resume_variant_owner_key" in names
        await engine.dispose()

    asyncio.run(verify())
    command.downgrade(configuration, "0015_company_intelligence")
    command.upgrade(configuration, "0016_resume_variants")
