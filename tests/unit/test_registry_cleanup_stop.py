"""A registry cleanup thread must stop and join without shadowing Thread._stop."""
from connectonion.network.host.session.active import ActiveSessionRegistry, start_cleanup_job


def test_stop_can_be_joined_repeatedly():
    job = start_cleanup_job(ActiveSessionRegistry(), interval=60)
    job.stop(timeout=1)
    job.stop(timeout=1)
    job.join(timeout=1)
    assert not job.is_alive()
