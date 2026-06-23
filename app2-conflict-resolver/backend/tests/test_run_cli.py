"""The pipeline CLI entry point (offline fast path)."""
from pipeline import run


def test_run_main_prints_summary(capsys):
    run.main()  # warm caches → no API call
    out = capsys.readouterr().out
    assert "Conflicts:" in out
    assert "Cost:" in out
