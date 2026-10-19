"""Keep audit records immutable and prevent deletion for three calendar years."""
from alembic import op

revision = '20261019_0006'
down_revision = '20261008_0005'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('''
        CREATE FUNCTION protect_audit_retention() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'TRUNCATE' THEN
                RAISE EXCEPTION 'Audit history cannot be truncated; minimum retention is three years';
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.dt_created_at + INTERVAL '3 years' > CURRENT_TIMESTAMP THEN
                    RAISE EXCEPTION 'Audit history must be retained for at least three years';
                END IF;
                RETURN OLD;
            ELSIF (to_jsonb(NEW) - ARRAY['dt_hmac_created_at','str_hmac_verification_status',
                       'str_country','str_country_name','str_city','str_region'])
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - ARRAY['dt_hmac_created_at','str_hmac_verification_status',
                       'str_country','str_country_name','str_city','str_region']) THEN
                RAISE EXCEPTION 'Signed audit history is immutable';
            END IF;
            RETURN NEW;
        END $$
    ''')
    op.execute('CREATE TRIGGER audit_retention_rows BEFORE UPDATE OR DELETE ON audit_logs '
               'FOR EACH ROW EXECUTE FUNCTION protect_audit_retention()')
    op.execute('CREATE TRIGGER audit_retention_truncate BEFORE TRUNCATE ON audit_logs '
               'FOR EACH STATEMENT EXECUTE FUNCTION protect_audit_retention()')


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('DROP TRIGGER IF EXISTS audit_retention_truncate ON audit_logs')
    op.execute('DROP TRIGGER IF EXISTS audit_retention_rows ON audit_logs')
    op.execute('DROP FUNCTION IF EXISTS protect_audit_retention()')
