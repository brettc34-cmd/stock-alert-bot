from services.run_cooldown_store import RunCooldownStore
import time


def test_sqlite_cooldown_persists_between_instances(tmp_path):
    db_path = tmp_path / "cooldowns.db"

    store1 = RunCooldownStore(redis_url=None, sqlite_path=str(db_path))
    store1.mark_run("guild:1", now_epoch=time.time())

    store2 = RunCooldownStore(redis_url=None, sqlite_path=str(db_path))
    remaining = store2.seconds_remaining("guild:1", cooldown_seconds=120)

    assert remaining > 0
