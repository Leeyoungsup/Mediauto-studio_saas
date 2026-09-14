"""Integration and comparison against a disposable local PostgreSQL cluster.

Set MEDIAUTO_TEST_POSTGRES_BIN to the directory containing initdb/pg_ctl.
No application connection string or production database is used.
"""

import asyncio
from contextlib import asynccontextmanager
import getpass
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.postgres.models import ApplicationDocument
from app.repositories import application_store as store
from app.repositories import project_store
from app import slide_store

MODEL_NAMES = [name for model in slide_store.LIST_AI_MODEL_KEYS
               for name in (model, slide_store._legacy_ai_model_key(model))]


def legacy_metrics(documents):
    metrics = {}
    for document in documents:
        relative = (document.get("str_rel_path") or "").replace("\\", "/").strip("/")
        project = relative.split("/", 1)[0] if relative else ""
        if not project:
            continue
        counts = metrics.setdefault(project, dict.fromkeys(("annotation_count", "review_count",
            "termination_count", "reviewed_count", "in_progress_count", "ai_analyzed_count"), 0))
        status = document.get("str_status") or ""
        annotation = document.get("str_annotation_status") or status
        counts["annotation_count"] += annotation in {"review", "done", "termination_in_progress", "termination", "flagged"}
        counts["review_count"] += annotation in {"termination_in_progress", "termination", "flagged"}
        counts["termination_count"] += annotation == "termination"
        counts["reviewed_count"] += status == "done"
        counts["in_progress_count"] += status in {"pending", "in_progress"}
        ai = document.get("dict_ai_results") or {}
        counts["ai_analyzed_count"] += any((ai.get(name) or {}).get("bool_has_result")
                                          for name in MODEL_NAMES)
    return metrics


@pytest.fixture(scope="module")
def disposable_postgres():
    binary_dir = os.environ.get("MEDIAUTO_TEST_POSTGRES_BIN")
    if not binary_dir:
        pytest.skip("Set MEDIAUTO_TEST_POSTGRES_BIN to run disposable PostgreSQL integration tests")
    binaries = Path(binary_dir)
    with tempfile.TemporaryDirectory(prefix="mediauto-test-pg-") as tmp:
        data = str(Path(tmp) / "data")
        subprocess.run([str(binaries / "initdb"), "-D", data, "-A", "trust", "--no-locale"],
                       check=True, capture_output=True)
        subprocess.run([str(binaries / "pg_ctl"), "-D", data, "-l", str(Path(tmp) / "server.log"),
                        "-o", f"-F -k {tmp} -h ''", "-w", "start"], check=True, capture_output=True)
        try:
            yield f"postgresql+asyncpg://{getpass.getuser()}@/postgres?host={tmp}"
        finally:
            subprocess.run([str(binaries / "pg_ctl"), "-D", data, "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True)


def test_queries_and_projection_benchmark(disposable_postgres, monkeypatch):
    async def exercise():
        engine = create_async_engine(disposable_postgres)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        @asynccontextmanager
        async def session_scope():
            async with factory() as session:
                yield session
                await session.commit()
        monkeypatch.setattr(store, "get_postgres_session", session_scope)
        monkeypatch.setattr(project_store, "get_postgres_session", session_scope)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(ApplicationDocument.__table__.create)
                await connection.execute(insert(ApplicationDocument), [
                    {"str_collection": "slides", "str_id": str(i), "str_natural_key": "project",
                     "str_secondary_key": f"slide-{i:05}.svs",
                     "dict_document": {"_id": str(i), "str_filename": f"slide-{i:05}.svs",
                         "str_rel_path": "project", "str_status": "done" if i % 2 else "pending",
                         "dict_large_unused": {"cells": list(range(1000))}, "nullable": None,
                         "dict_ai_results": {"Quanti HE": {"bool_has_result": i % 3 == 0}}}}
                    for i in range(1500)
                ])
            collection = store.PostgresDocumentCollection("slides")
            metrics = await project_store.get_project_metrics(MODEL_NAMES)
            assert metrics == {"project": {"annotation_count": 750, "review_count": 0,
                                          "termination_count": 0, "reviewed_count": 750,
                                          "in_progress_count": 750, "ai_analyzed_count": 500}}
            projection = {"str_filename": 1, "str_status": 1, "nullable": 1, "absent": 1, "_id": 0}
            rows = await collection.find({}, projection).to_list(length=50)
            assert len(rows) == 50
            assert all(set(row) == {"str_filename", "str_status", "nullable"} for row in rows)
            assert all(row["nullable"] is None for row in rows)
            single = await collection.find_one({"_id": "42"}, projection)
            assert single["str_filename"] == "slide-00042.svs"
            excluded = await collection.find_one({"_id": "42"}, {"dict_large_unused": 0})
            assert "dict_large_unused" not in excluded
            assert excluded["_id"] == "42"
            nested = await collection.find_one({"_id": "42"}, {"dict_ai_results.Quanti HE": 1, "_id": 0})
            assert nested == {"dict_ai_results": {"Quanti HE": {"bool_has_result": True}}}
            assert await collection.find({}).limit(0).to_list() == []
            all_rows = await collection._find_documents({})
            query = {"$or": [{"str_status": "done"}, {"str_filename": {"$regex": "00000"}}]}
            expected = [store.apply_projection(row, projection) for row in all_rows if store.document_matches(row, query)][3:10]
            actual = await collection.find(query, projection).skip(3).limit(20).to_list(length=7)
            assert actual == expected
            ordered = await collection.find({}, projection).sort("str_filename", -1).limit(7).to_list()
            assert ordered == [store.apply_projection(row, projection) for row in
                               sorted(all_rows, key=lambda row: row["str_filename"], reverse=True)[:7]]

            async def old_page():
                candidates = await collection._find_documents({})
                return [store.apply_projection(row, projection) for row in candidates[:50]]
            async def new_page():
                return await collection.find({}, projection).limit(50).to_list()
            async def old_metrics():
                return legacy_metrics(await collection._find_documents({}))
            async def new_metrics():
                return await project_store.get_project_metrics(MODEL_NAMES)
            assert await old_page() == await new_page()
            assert await old_metrics() == await new_metrics()
            timings = {}
            for name, operation in (("before", old_page), ("after", new_page),
                                    ("project_before", old_metrics), ("project_after", new_metrics)):
                await operation()
                samples = []
                for _ in range(5):
                    start = time.perf_counter()
                    await operation()
                    samples.append((time.perf_counter() - start) * 1000)
                timings[name + "_median_ms"] = round(statistics.median(samples), 2)
            timings.update(rows=1500, page_size=50,
                           before_json_bytes=len(json.dumps(all_rows).encode()),
                           after_json_bytes=len(json.dumps(await new_page()).encode()))
            print("\nDOCUMENT_PAGE_BENCHMARK " + json.dumps(timings))

            # Legacy flags, missing/null status fields, and Windows paths must
            # retain the same dashboard counts after moving aggregation to SQL.
            edge_documents = [
                {"str_rel_path": "\\edge\\folder\\", "str_status": status,
                 "str_annotation_status": annotation,
                 "dict_ai_results": {"HE-Fit": {"bool_has_result": flag}}}
                for status, annotation, flag in [
                    ("done", "termination", True), ("pending", "", False),
                    ("", "flagged", None), ("done", None, 1), ("in_progress", "review", "yes"),
                    (None, None, {}), (None, "termination_in_progress", []),
                ]
            ] + [{"str_rel_path": ""}, {"str_rel_path": "/edge/", "str_status": "done"}]
            async with engine.begin() as connection:
                await connection.execute(insert(ApplicationDocument), [
                    {"str_collection": "slides", "str_id": f"edge-{i}",
                     "str_natural_key": "edge", "str_secondary_key": str(i),
                     "dict_document": {"_id": f"edge-{i}", **document}}
                    for i, document in enumerate(edge_documents)
                ])
            assert await old_metrics() == await new_metrics()
        finally:
            await engine.dispose()
    asyncio.run(exercise())
