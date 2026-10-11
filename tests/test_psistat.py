"""Unit tests for psistat.

These focus on the pure/parsing helpers so they run without touching
/proc/pressure or initializing a curses window.
"""

import psistat


def test_ago_str_seconds():
    assert psistat.ago_str(0) == ' 0s'
    assert psistat.ago_str(45) == '45s'


def test_ago_str_minutes():
    assert psistat.ago_str(90) == '1m30s'


def test_ago_str_hours():
    assert psistat.ago_str(3600) == '1h00m'
    assert psistat.ago_str(3 * 3600 + 7 * 60) == '3h07m'


def test_ago_str_negative_uses_magnitude():
    assert psistat.ago_str(-90) == psistat.ago_str(90)


def test_pressure_group_pattern_parses_proc_line():
    line = 'some avg10=0.00 avg60=1.23 avg300=4.56 total=789012345'
    match = psistat.PressureGroup.pattern.match(line)
    assert match is not None
    assert match.group(1) == 'some'
    assert match.group(2) == '1.23'
    assert match.group(3) == '4.56'
    assert match.group(4) == '789012345'


def test_pressure_group_pattern_rejects_garbage():
    assert psistat.PressureGroup.pattern.match('nonsense line') is None


def test_console_window_body_api_matches_pinned_version():
    """console-window >= 1.4 renamed put_body -> add_body."""
    from console_window import ConsoleWindow, OptionSpinner

    assert hasattr(ConsoleWindow, 'add_body')
    assert not hasattr(ConsoleWindow, 'put_body')
    assert hasattr(ConsoleWindow, 'add_header')
    assert hasattr(OptionSpinner, 'show_help_nav_keys')
    assert hasattr(OptionSpinner, 'show_help_body')


def test_no_stale_put_body_references():
    import inspect

    assert 'put_body' not in inspect.getsource(psistat)


def test_console_window_poll_timeout_supports_1s_sampling():
    """ConsoleWindow.prompt() only re-checks the elapsed time between getch()
    calls, so getch's timeout must be well under our ~1s sampling interval.
    Otherwise the loop runs every ~2s, count_valid_samples() rejects the gaps,
    and the 1s/3s/10s averages show 'n/a' forever."""
    from console_window import ConsoleWindow

    assert ConsoleWindow.timeout_ms <= 1000
