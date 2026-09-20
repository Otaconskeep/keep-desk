"""Regression: briefing precedence must not let old failures hijack a completed mission."""
from __future__ import annotations

from briefing import (
    select_briefing_mode,
    _latest_completed_mission,
    _latest_failure_without_newer_success,
    _newest_failure,
)


def _driver(done, failed, *, running=None, queued=None, approvals=None):
    completed = _latest_completed_mission(done)
    newest_failure = _newest_failure(failed)
    failure_driver = None
    if newest_failure and (
        not completed
        or (newest_failure.get('finished_at') or '') > (completed.get('finished_at') or '')
    ):
        failure_driver = newest_failure
    mode = select_briefing_mode(
        running=running or [],
        queued=queued or [],
        completed=completed,
        approvals=approvals or [],
        failure=failure_driver,
    )
    return mode, completed, failure_driver


def test_completed_beats_older_failure():
    done = [{
        'id': 'done1', 'status': 'done', 'title': 'Capability proof',
        'finished_at': '2026-09-19T20:00:00+00:00',
    }]
    failed = [{
        'id': 'fail1', 'status': 'failed', 'title': 'Mission: rooms + AI YouTube',
        'finished_at': '2026-09-19T19:00:00+00:00', 'result_summary': 'looped',
    }]
    mode, completed, failure_driver = _driver(done, failed)
    assert completed and completed['id'] == 'done1'
    assert failure_driver is None
    assert mode == 'completed'
    assert _latest_failure_without_newer_success(done, failed) is None


def test_newer_failure_is_latest_outcome():
    done = [{
        'id': 'done1', 'status': 'done', 'title': 'Old success',
        'finished_at': '2026-09-18T12:00:00+00:00',
    }]
    failed = [{
        'id': 'fail2', 'status': 'failed', 'title': 'New attempt',
        'finished_at': '2026-09-19T21:00:00+00:00', 'result_summary': 'brain error',
    }]
    mode, _, failure_driver = _driver(done, failed)
    assert failure_driver and failure_driver['id'] == 'fail2'
    assert mode == 'failure'


def test_failure_only_when_no_completed():
    failed = [{
        'id': 'fail1', 'status': 'failed', 'title': 'Only failure',
        'finished_at': '2026-09-19T21:00:00+00:00',
    }]
    mode, _, failure_driver = _driver([], failed)
    assert mode == 'failure'
    assert failure_driver and failure_driver['id'] == 'fail1'


def test_active_overrides_while_running():
    done = [{
        'id': 'done1', 'status': 'done', 'title': 'Done',
        'finished_at': '2026-09-19T20:00:00+00:00',
    }]
    running = [{'id': 'run1', 'status': 'running', 'title': 'New work', 'bot_id': 'engineer'}]
    mode, _, _ = _driver(done, [], running=running, approvals=[{'id': 'a'}])
    assert mode == 'active'


def test_completed_beats_blocker():
    done = [{
        'id': 'done1', 'status': 'done', 'title': 'Done',
        'finished_at': '2026-09-19T20:00:00+00:00',
    }]
    mode, _, _ = _driver(done, [], approvals=[{'id': 'a'}])
    assert mode == 'completed'


def test_blocker_when_idle_without_completed():
    mode, _, _ = _driver([], [], approvals=[{'id': 'a'}])
    assert mode == 'blocker'


def test_ready_when_empty():
    mode, _, _ = _driver([], [])
    assert mode == 'ready'


if __name__ == '__main__':
    test_completed_beats_older_failure()
    test_newer_failure_is_latest_outcome()
    test_failure_only_when_no_completed()
    test_active_overrides_while_running()
    test_completed_beats_blocker()
    test_blocker_when_idle_without_completed()
    test_ready_when_empty()
    print('PASS all briefing precedence tests')
