"""
Shared pytest fixtures for AlphaSystem V3 tests.
"""
import os
import sys
import tempfile
import shutil
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test data, cleaned up after test."""
    d = tempfile.mkdtemp(prefix="alpha_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)
