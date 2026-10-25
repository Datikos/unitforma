"""Helpers to apply the standard tenant RLS policy set to a table (plan §3.4).

Policies:
* ``tenant_isolation`` — rows visible/writable only when ``tenant_id`` equals the
  transaction-local ``app.tenant_id`` setting (empty setting → no rows).
* ``platform_scope`` — platform administrators (``app.scope = 'platform'``) see all rows.

``FORCE ROW LEVEL SECURITY`` makes the owner role subject to the policies too.
"""

from __future__ import annotations

from alembic import op


def enable_tenant_rls(table: str, tenant_column: str = "tenant_id") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
          USING ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        f"""
        CREATE POLICY platform_scope ON {table}
          USING (current_setting('app.scope', true) = 'platform')
          WITH CHECK (current_setting('app.scope', true) = 'platform')
        """
    )


def disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"DROP POLICY IF EXISTS platform_scope ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
