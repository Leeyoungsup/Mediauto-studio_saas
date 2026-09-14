"""Project dashboard counts aggregated in PostgreSQL."""

import json

from sqlalchemy import case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.postgres.database import get_postgres_session
from app.postgres.models import ApplicationDocument


def project_metrics_statement(model_names):
    document = ApplicationDocument.dict_document
    # Materialize only small dashboard fields once. Without this boundary the
    # planner can repeatedly decompress the full JSONB for every model/count.
    source = select(
        document["str_rel_path"].as_string().label("relative"),
        document["str_status"].as_string().label("status"),
        document["str_annotation_status"].as_string().label("annotation"),
        document["dict_ai_results"].label("ai"),
    ).where(ApplicationDocument.str_collection == "slides").cte("project_metrics_source")
    source = source.prefix_with("MATERIALIZED", dialect="postgresql")
    relative = func.trim(func.replace(func.coalesce(source.c.relative, ""), "\\", "/"), "/")
    project = func.split_part(relative, "/", 1)
    status = func.coalesce(source.c.status, "")
    annotation = func.coalesce(func.nullif(source.c.annotation, ""), status)
    flags = []
    for name in model_names:
        value = source.c.ai[name]["bool_has_result"]
        # Match Python truthiness for JSON values, including legacy records.
        flags.append(func.coalesce(value.not_in([
            cast(literal(json.dumps(item)), JSONB) for item in (None, False, 0, "", [], {})
        ]), False))
    conditions = {
        "annotation_count": annotation.in_(("review", "done", "termination_in_progress", "termination", "flagged")),
        "review_count": annotation.in_(("termination_in_progress", "termination", "flagged")),
        "termination_count": annotation == "termination",
        "reviewed_count": status == "done",
        "in_progress_count": status.in_(("pending", "in_progress")),
        "ai_analyzed_count": or_(*flags) if flags else False,
    }
    return select(project.label("project"), *[
        func.sum(case((condition, 1), else_=0)).label(name)
        for name, condition in conditions.items()
    ]).where(project != "").group_by(project)


async def get_project_metrics(model_names):
    async with get_postgres_session() as session:
        rows = (await session.execute(project_metrics_statement(model_names))).mappings()
        return {row["project"]: {key: int(value) for key, value in row.items() if key != "project"}
                for row in rows}
