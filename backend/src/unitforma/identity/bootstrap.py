"""First platform administrator: `unitforma bootstrap-admin <email>`.

The person first signs in once at app.<domain> (which creates the Kratos identity and the
``users`` row); this command then flags that user as platform admin. If no ``users`` row
exists yet, the Kratos identity is looked up by email and the row is created.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import get_sessionmaker
from unitforma.core.ids import new_id
from unitforma.identity.kratos import KratosClient
from unitforma.tenants.models import User

log = structlog.get_logger()


async def bootstrap_platform_admin(email: str) -> int:
    email = email.lower().strip()
    async with get_sessionmaker()() as db:
        async with db.begin():
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                kratos = KratosClient()
                try:
                    identity = await kratos.find_identity_by_email(email)
                finally:
                    await kratos.aclose()
                if identity is None:
                    log.error("bootstrap.identity_missing", email=email)
                    print(f"No Kratos identity for {email}: sign in once first, then re-run.")
                    return 1
                user = User(id=new_id(), kratos_identity_id=uuid.UUID(identity["id"]), email=email)
                db.add(user)
            user.is_platform_admin = True
    print(f"{email} is now a platform administrator.")
    return 0
