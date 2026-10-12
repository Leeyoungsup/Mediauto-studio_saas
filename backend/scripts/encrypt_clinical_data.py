"""Inspect or encrypt legacy clinical DB copies; defaults to a read-only preview.

Run with the application's existing environment and encryption key after backup:
    cd backend && python -m scripts.encrypt_clinical_data
    cd backend && python -m scripts.encrypt_clinical_data --apply
Never prints keys, clinical values, case names, or connection strings.
"""
import argparse
import asyncio
import json

from sqlalchemy import select
from app.encryption import ENCRYPTED_JSON_MARKER, encrypt_json, decrypt_json
from app.postgres.database import connect_postgres, disconnect_postgres, get_postgres_session
from app.postgres.models import ApplicationDocument, CaseClinicalInfo
from app.repositories.application_store import encode_document_value, decode_document_value


async def convert(session, *, apply=False):
    counts = {"clinical_rows": 0, "slide_copies": 0, "already_encrypted": 0}
    for model, attribute, count_key in ((CaseClinicalInfo, "dict_clinical_info", "clinical_rows"),
                                         (ApplicationDocument, "dict_document", "slide_copies")):
        query = select(model)
        if model is ApplicationDocument:
            query = query.where(ApplicationDocument.str_collection == "slides")
        if apply:
            query = query.with_for_update()
        stream = await session.stream_scalars(query.execution_options(yield_per=25))
        try:
            async for row in stream:
                value = getattr(row, attribute)
                clinical = value if model is CaseClinicalInfo else value.get("dict_clinical_info")
                if not isinstance(clinical, dict):
                    continue
                if ENCRYPTED_JSON_MARKER in clinical:
                    decrypt_json(clinical)  # Verify the current key even during preview.
                    counts["already_encrypted"] += 1
                    continue
                counts[count_key] += 1
                if apply:
                    encoded = encrypt_json(clinical) if model is CaseClinicalInfo else encode_document_value(decode_document_value(value))
                    setattr(row, attribute, encoded)
        finally:
            await stream.close()
    return counts


async def run(apply):
    try:
        await connect_postgres()
        async with get_postgres_session() as session:
            counts = await convert(session, apply=apply)
        print(json.dumps({"mode": "apply" if apply else "preview", **counts}))
    finally:
        await disconnect_postgres()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
