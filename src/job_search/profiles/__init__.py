"""Candidate profile management."""

from job_search.profiles.service import (
    ProfileValidationResult,
    load_profile_file,
    load_template_dict,
    save_profile,
    template_path,
    validate_profile_dict,
    validate_profile_file,
)

__all__ = [
    "ProfileValidationResult",
    "load_profile_file",
    "load_template_dict",
    "save_profile",
    "template_path",
    "validate_profile_dict",
    "validate_profile_file",
]
