"""
Tests for run_pipeline.py
==========================
Pipeline orchestration: run_step success/failure, timing, step functions,
and _force_remove_dir cross-platform logic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# run_pipeline.py imports dotenv at module level; stub it if not installed
import importlib
try:
    importlib.import_module("dotenv")
except ModuleNotFoundError:
    import types as _types
    dotenv_stub = _types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *a, **kw: None
    sys.modules.setdefault("dotenv", dotenv_stub)

# loguru stub so we don't need it installed in CI
try:
    importlib.import_module("loguru")
except ModuleNotFoundError:
    import types as _types
    loguru_stub = _types.ModuleType("loguru")
    _l = MagicMock()
    loguru_stub.logger = _l
    sys.modules.setdefault("loguru", loguru_stub)

import run_pipeline
from run_pipeline import _force_remove_dir, run_step


# ─────────────────────────────────────────────────────────────────────────────
# run_step
# ─────────────────────────────────────────────────────────────────────────────

class TestRunStep:
    def test_returns_true_on_success(self):
        ok = run_step("Test step", lambda: None)
        assert ok is True

    def test_returns_false_on_exception(self):
        def boom():
            raise ValueError("intentional failure")

        ok = run_step("Failing step", boom)
        assert ok is False

    def test_calls_function_with_args(self):
        spy = MagicMock()
        run_step("Step with args", spy, 1, 2, key="value")
        spy.assert_called_once_with(1, 2, key="value")

    def test_calls_function_with_no_args(self):
        spy = MagicMock()
        run_step("No-arg step", spy)
        spy.assert_called_once_with()

    def test_does_not_re_raise_exception(self):
        """run_step must swallow all exceptions and return False."""
        def raises():
            raise RuntimeError("should be caught")

        try:
            result = run_step("Swallow", raises)
        except Exception:
            pytest.fail("run_step re-raised an exception — it should not")
        assert result is False

    def test_returns_bool_not_none(self):
        result = run_step("Bool check", lambda: None)
        assert isinstance(result, bool)

    def test_measures_elapsed_time(self):
        """run_step should call time.time() to measure duration."""
        call_count = [0]
        original_time = __import__("time").time

        def counting_time():
            call_count[0] += 1
            return original_time()

        with patch("time.time", side_effect=counting_time):
            run_step("Timed step", lambda: None)

        assert call_count[0] >= 2  # at least t0 and elapsed


# ─────────────────────────────────────────────────────────────────────────────
# step_ingest_tfl
# ─────────────────────────────────────────────────────────────────────────────

class TestStepIngestTfl:
    def test_calls_tfl_run(self):
        mock_run = MagicMock()
        with patch.dict("sys.modules", {
            "ingestion": MagicMock(),
            "ingestion.ingest_tfl_cycling": MagicMock(run=mock_run),
        }):
            run_pipeline.step_ingest_tfl()
        mock_run.assert_called_once()

    def test_propagates_exception(self):
        mock_mod = MagicMock()
        mock_mod.run.side_effect = RuntimeError("network error")
        with patch.dict("sys.modules", {
            "ingestion": MagicMock(),
            "ingestion.ingest_tfl_cycling": mock_mod,
        }):
            with pytest.raises(RuntimeError, match="network error"):
                run_pipeline.step_ingest_tfl()


# ─────────────────────────────────────────────────────────────────────────────
# step_ingest_accidents
# ─────────────────────────────────────────────────────────────────────────────

class TestStepIngestAccidents:
    def test_calls_accidents_run(self):
        mock_run = MagicMock()
        with patch.dict("sys.modules", {
            "ingestion": MagicMock(),
            "ingestion.ingest_uk_accidents": MagicMock(run=mock_run),
        }):
            run_pipeline.step_ingest_accidents()
        mock_run.assert_called_once()

    def test_propagates_exception(self):
        mock_mod = MagicMock()
        mock_mod.run.side_effect = RuntimeError("download fail")
        with patch.dict("sys.modules", {
            "ingestion": MagicMock(),
            "ingestion.ingest_uk_accidents": mock_mod,
        }):
            with pytest.raises(RuntimeError):
                run_pipeline.step_ingest_accidents()


# ─────────────────────────────────────────────────────────────────────────────
# _force_remove_dir
# ─────────────────────────────────────────────────────────────────────────────

class TestForceRemoveDir:
    def test_does_nothing_when_path_missing(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        _force_remove_dir(missing)  # should not raise

    def test_non_windows_uses_shutil_rmtree(self, tmp_path):
        target = tmp_path / "to_remove"
        target.mkdir()
        (target / "file.txt").write_text("hello")

        with patch.object(sys, "platform", "linux"):
            import shutil
            with patch("shutil.rmtree") as mock_rmtree:
                _force_remove_dir(target)
            mock_rmtree.assert_called()

    def test_windows_uses_robocopy_and_rmdir(self, tmp_path):
        target = tmp_path / "to_remove"
        target.mkdir()

        with patch.object(sys, "platform", "win32"):
            with patch("subprocess.run") as mock_run:
                with patch("time.sleep"):
                    # Make path.exists() return False after rmdir so it terminates
                    with patch.object(Path, "exists", side_effect=[True, False, False]):
                        _force_remove_dir(target)

            # Should have called robocopy and rmdir
            calls_flat = [str(c) for c in mock_run.call_args_list]
            assert any("robocopy" in c for c in calls_flat)
            assert any("rmdir" in c for c in calls_flat)

    def test_windows_shutil_fallback_when_path_persists(self, tmp_path):
        target = tmp_path / "stubborn_dir"
        target.mkdir()

        with patch.object(sys, "platform", "win32"):
            with patch("subprocess.run"):
                with patch("time.sleep"):
                    with patch("shutil.rmtree") as mock_rmtree:
                        # exists() True always (simulating robocopy failing to clear it)
                        with patch.object(Path, "exists", return_value=True):
                            _force_remove_dir(target)
                    mock_rmtree.assert_called()
