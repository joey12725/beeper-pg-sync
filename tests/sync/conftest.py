import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from beeper_pg_sync.db import connect, migrate  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def dsn():
    if not DSN:
        pytest.skip("set TEST_DATABASE_URL to run database tests")
    return DSN


@pytest.fixture
def conn(dsn):
    with connect(dsn) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        migrate(c)
        yield c
