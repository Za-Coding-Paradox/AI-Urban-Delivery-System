# backend/tests/test_profile_manager.py

import pytest

from engine.grid_builder import GridBuilder
from engine.profile_manager import ProfileManager, ProfileManagerError


@pytest.fixture
def manager(tmp_path):
    """
    tmp_path is a pytest built-in that gives each test
    its own temporary folder that is deleted after the test.
    We never pollute the real profiles/ directory during testing.
    """
    return ProfileManager(profiles_dir=tmp_path)


def test_list_empty_initially(manager):
    assert manager.list() == []


def test_generate_returns_valid_profile(manager):
    profile = manager.generate(seed=42)
    assert profile["meta"]["seed"] == 42
    assert len(profile["grid"]["cells"]) == 225
    assert len(profile["deliveries"]["destinations"]) == 5


def test_generate_is_deterministic(manager):
    profile_a = manager.generate(seed=42)
    profile_b = manager.generate(seed=42)
    # Same seed → same base position, same obstacles, same deliveries
    assert profile_a["robot"]["start"] == profile_b["robot"]["start"]
    assert profile_a["deliveries"]["destinations"] == profile_b["deliveries"]["destinations"]


def test_generate_different_seeds_differ(manager):
    profile_a = manager.generate(seed=1)
    profile_b = manager.generate(seed=2)
    # Extremely unlikely to be identical
    assert (
        profile_a["robot"]["start"] != profile_b["robot"]["start"]
        or profile_a["deliveries"]["destinations"] != profile_b["deliveries"]["destinations"]
    )


def test_save_and_load_roundtrip(manager):
    profile = manager.generate(seed=99)
    manager.save(profile, "test_profile")

    loaded = manager.load("test_profile")
    assert loaded["meta"]["seed"] == 99
    assert loaded["grid"]["cells"] == profile["grid"]["cells"]


def test_list_shows_saved_profile(manager):
    profile = manager.generate(seed=7)
    manager.save(profile, "my_city")
    assert "my_city" in manager.list()


def test_load_nonexistent_raises(manager):
    with pytest.raises(ProfileManagerError, match="not found"):
        manager.load("does_not_exist")


def test_generated_profile_passes_grid_builder(manager):
    """
    The real end-to-end check — GridBuilder must accept what ProfileManager generates.
    If this passes, the two components are correctly integrated.
    """
    profile = manager.generate(seed=123)
    cells = GridBuilder().build(profile)
    assert len(cells) == 225


def test_multiple_seeds_all_buildable(manager):
    """Stress test — 10 different seeds must all produce buildable grids."""
    for seed in range(10):
        profile = manager.generate(seed=seed)
        cells = GridBuilder().build(profile)
        assert len(cells) == 225
