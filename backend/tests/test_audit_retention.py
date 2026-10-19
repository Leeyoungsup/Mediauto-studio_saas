"""Run only in the isolated, migrated PostgreSQL test database."""
import asyncio
import os
import uuid
from datetime import datetime,timedelta,timezone

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def test_database_enforces_retention_immutability_and_allows_verification_metadata():
    uri=os.environ.get('SECURITY_TEST_DATABASE_URI','')
    if not uri:pytest.skip('Disposable PostgreSQL required')
    parsed=make_url(uri)
    assert parsed.host=='127.0.0.1' and parsed.database=='knuch_security_test'
    async def run():
        engine=create_async_engine(uri)
        identifier=uuid.uuid4().hex[:24]
        try:
            async with engine.begin() as connection:
                await connection.execute(text("INSERT INTO audit_logs(id,str_action,dt_created_at,str_detail,str_ip_address,str_user_agent,str_hmac_verification_status,str_prev_hmac,str_hmac,str_country,str_country_name,str_city,str_region,dict_extra) VALUES (:id,'test.retention',CURRENT_TIMESTAMP,'','','','unknown','','','','','','','{}')"),{'id':identifier})
            for sql in ["DELETE FROM audit_logs WHERE id=:id", "UPDATE audit_logs SET dt_created_at=TIMESTAMP '2000-01-01' WHERE id=:id", "UPDATE audit_logs SET str_action='tampered' WHERE id=:id", 'TRUNCATE audit_logs']:
                with pytest.raises(Exception,match='three years|immutable|truncated'):
                    async with engine.begin() as connection:await connection.execute(text(sql),{'id':identifier})
            async with engine.begin() as connection:
                await connection.execute(text("UPDATE audit_logs SET str_city='Seoul',str_hmac_verification_status='valid' WHERE id=:id"),{'id':identifier})
                assert await connection.scalar(text('SELECT count(*) FROM audit_logs WHERE id=:id'),{'id':identifier})==1
                await connection.execute(text("INSERT INTO audit_logs(id,str_action,dt_created_at,str_detail,str_ip_address,str_user_agent,str_hmac_verification_status,str_prev_hmac,str_hmac,str_country,str_country_name,str_city,str_region,dict_extra) SELECT id||'-old',str_action,CURRENT_TIMESTAMP-INTERVAL '4 years',str_detail,str_ip_address,str_user_agent,str_hmac_verification_status,str_prev_hmac,str_hmac,str_country,str_country_name,str_city,str_region,dict_extra FROM audit_logs WHERE id=:id"),{'id':identifier})
                result=await connection.execute(text("DELETE FROM audit_logs WHERE id=:id"),{'id':identifier+'-old'})
                assert result.rowcount==1
        finally:await engine.dispose()
    asyncio.run(run())
