"""Tests for profile template, validation, and save helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_search.profiles.service import (
    load_template_dict,
    save_profile,
    validate_profile_dict,
    validate_profile_file,
)
from job_search.schemas.candidate import CandidateProfile, SkillEntry


def test_load_template_dict_has_required_fields():
    data = load_template_dict()
    assert "name" in data
    assert "skills" in data
    assert "skills_to_learn" in data
    assert "target_roles" in data


def test_validate_profile_dict_accepts_junior_data_profile():
    data = {
        "name": "jan_kowalski",
        "target_sectors": ["data"],
        "target_roles": ["Junior Data Engineer"],
        "skills": [{"name": "Python", "level": "junior", "years": 1}],
        "skills_to_learn": ["Spark", "PySpark", "Databricks"],
        "cv_text": "Junior data engineer.",
    }
    result = validate_profile_dict(data)
    assert result.errors == []
    assert result.profile is not None
    assert result.profile.name == "jan_kowalski"


def test_validate_profile_dict_rejects_invalid_name():
    data = {
        "name": "Jan Kowalski",
        "target_roles": ["Data Analyst"],
        "skills": [{"name": "SQL"}],
    }
    result = validate_profile_dict(data)
    assert result.profile is None
    assert any("name" in err.lower() for err in result.errors)


def test_validate_profile_dict_warns_on_missing_skills():
    data = {
        "name": "minimal",
        "target_roles": [],
        "skills": [],
    }
    result = validate_profile_dict(data)
    assert result.profile is not None
    assert any("skills" in w.lower() for w in result.warnings)


def test_validate_profile_file_reads_default_json():
    path = Path("config/profiles/default.json")
    if not path.is_file():
        pytest.skip("default.json not present")
    result = validate_profile_file(path)
    assert result.errors == []
    assert result.profile is not None
    assert "Spark" in {s.name for s in result.profile.skills}


def test_save_profile_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "job_search.profiles.service.profiles_directory",
        lambda: tmp_path,
    )
    profile = CandidateProfile(
        name="test_user",
        target_roles=["Junior Data Engineer"],
        skills=[SkillEntry(name="Python", level="junior")],
        skills_to_learn=["Databricks"],
    )
    saved = save_profile(profile)
    assert saved.is_file()
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded["name"] == "test_user"
    assert loaded["skills_to_learn"] == ["Databricks"]
