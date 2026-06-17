"""Profile template, validation, and persistence helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from job_search.schemas.candidate import CandidateProfile

PROFILE_TEMPLATE_PATH = Path("config/profiles/profile.template.json")
PROFILES_DIR = Path("config/profiles")


@dataclass
class ProfileValidationResult:
    profile: CandidateProfile | None
    errors: list[str]
    warnings: list[str]


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def template_path() -> Path:
    return get_repo_root() / PROFILE_TEMPLATE_PATH


def profiles_directory() -> Path:
    return get_repo_root() / PROFILES_DIR


def load_template_dict() -> dict:
    path = template_path()
    if not path.is_file():
        raise FileNotFoundError(f"Brak szablonu profilu: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile_file(path: Path) -> CandidateProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


def validate_profile_dict(data: dict) -> ProfileValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ProfileValidationResult(None, ["Profil musi być obiektem JSON."], [])

    try:
        profile = CandidateProfile.model_validate(data)
    except ValidationError as exc:
        for issue in exc.errors():
            location = ".".join(str(part) for part in issue.get("loc", ()))
            errors.append(f"{location}: {issue.get('msg', 'niepoprawna wartość')}")
        return ProfileValidationResult(None, errors, warnings)

    if not profile.target_roles:
        warnings.append("Brak target_roles — matching może być mniej precyzyjny.")
    if not profile.skills:
        warnings.append("Brak skills — dodaj przynajmniej Python/SQL dla lepszego dopasowania.")
    if not profile.cv_text:
        warnings.append("Brak cv_text — LLM ma mniej kontekstu o kandydacie.")

    name = profile.name.strip()
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        errors.append(
            "Pole name może zawierać tylko małe litery, cyfry, _ i - (np. jan_kowalski)."
        )
        return ProfileValidationResult(None, errors, warnings)

    return ProfileValidationResult(profile, errors, warnings)


def validate_profile_file(path: Path) -> ProfileValidationResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ProfileValidationResult(None, [f"Niepoprawny JSON: {exc.msg}"], [])
    return validate_profile_dict(data)


def save_profile(profile: CandidateProfile, *, filename: str | None = None) -> Path:
    profiles_directory().mkdir(parents=True, exist_ok=True)
    safe_name = filename or f"{profile.name}.json"
    if not safe_name.endswith(".json"):
        safe_name = f"{safe_name}.json"
    target = profiles_directory() / safe_name
    payload = profile.model_dump(mode="json")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def list_profile_files() -> list[Path]:
    directory = profiles_directory()
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob("*.json") if path.name != "profile.template.json"
    )
