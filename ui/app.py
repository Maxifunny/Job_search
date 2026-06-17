"""Streamlit UI — client-friendly job search dashboard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from shlex import quote
from typing import Callable

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from job_search.profiles import (  # noqa: E402
    load_template_dict,
    save_profile,
    validate_profile_dict,
)
from ui.components import (  # noqa: E402
    render_cards_from_rows,
    render_loading_steps,
    render_status_summary,
)
from ui.data_access import (  # noqa: E402
    SUPPORTED_SOURCES,
    database_path_from_url,
    detect_env_status,
    fetch_latest_status,
    fetch_offers,
    fetch_recommendations,
    get_repo_root,
    list_profiles_for_ui,
    list_sectors_for_ui,
)

PIPELINE_STEPS = [
    "Przygotowanie bazy danych",
    "Pobieranie ofert z portali",
    "Zapisywanie ofert",
    "Dopasowywanie do profilu",
    "Gotowe",
]


def _default_state() -> None:
    defaults = {
        "last_output": "",
        "last_status": None,
        "last_command": "",
        "db_prepared": False,
        "pipeline_running": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _run_command(command: list[str], on_line: Callable[[str], None] | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    process = subprocess.Popen(
        command,
        cwd=str(get_repo_root()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    output_lines: list[str] = []
    if process.stdout is not None:
        for line in process.stdout:
            stripped = line.rstrip("\n")
            output_lines.append(stripped)
            if on_line is not None:
                on_line(stripped)
    return process.wait(), "\n".join(output_lines)


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _status_from_output(output: str) -> dict[str, int]:
    summary = {
        "scraped": 0,
        "new": 0,
        "updated": 0,
        "evaluated": 0,
        "accepted": 0,
        "rejected": 0,
        "skipped": 0,
        "errors": 0,
    }
    for line in output.splitlines():
        if line.startswith("[") and "found=" in line and "new=" in line and "updated=" in line:
            parts = line.replace("[", " ").replace("]", " ").split()
            for part in parts:
                if part.startswith("found="):
                    summary["scraped"] += _safe_int(part.removeprefix("found="))
                elif part.startswith("new="):
                    summary["new"] += _safe_int(part.removeprefix("new="))
                elif part.startswith("updated="):
                    summary["updated"] += _safe_int(part.removeprefix("updated="))
        if "evaluated=" in line and "accepted=" in line and "rejected=" in line:
            parts = line.split()
            for part in parts:
                if part.startswith("evaluated="):
                    summary["evaluated"] = _safe_int(part.removeprefix("evaluated="))
                elif part.startswith("accepted="):
                    summary["accepted"] = _safe_int(part.removeprefix("accepted="))
                elif part.startswith("rejected="):
                    summary["rejected"] = _safe_int(part.removeprefix("rejected="))
                elif part.startswith("skipped="):
                    summary["skipped"] = _safe_int(part.removeprefix("skipped="))
        if "Błędy" in line or "failed:" in line.lower() or "error" in line.lower():
            summary["errors"] += 1
    return summary


def _detect_pipeline_step(line: str, current: str) -> str:
    lowered = line.lower()
    if "evaluated=" in line:
        return "Dopasowywanie do profilu"
    if "found=" in line and "new=" in line:
        return "Pobieranie ofert z portali"
    if "rekomendacje" in lowered or "[ok]" in lowered:
        return "Gotowe"
    if "database" in lowered or "migrate" in lowered or "initialized" in lowered:
        return "Przygotowanie bazy danych"
    return current


def _ensure_database_ready(db_path: Path | None) -> bool:
    if st.session_state.get("db_prepared"):
        return True
    if db_path is None:
        st.session_state["db_prepared"] = True
        return True

    setup_logs: list[str] = []
    if not db_path.exists():
        init_cmd = [sys.executable, "-m", "job_search.cli", "init-db"]
        code, output = _run_command(init_cmd)
        setup_logs.append(f"$ {' '.join(quote(p) for p in init_cmd)}\n{output}".strip())
        if code != 0:
            st.session_state["last_output"] = "\n\n".join(setup_logs)
            st.error("Nie udało się zainicjalizować bazy danych.")
            return False

    migrate_cmd = [sys.executable, "-m", "job_search.cli", "migrate"]
    code, output = _run_command(migrate_cmd)
    setup_logs.append(f"$ {' '.join(quote(p) for p in migrate_cmd)}\n{output}".strip())
    st.session_state["last_output"] = "\n\n".join(setup_logs)
    if code != 0:
        st.error("Baza danych nie jest gotowa.")
        return False

    st.session_state["db_prepared"] = True
    return True


def _run_pipeline(
    *,
    sector: str,
    profile: str,
    source: str,
    max_offers: int,
    match_limit: int,
    sync_vectors: bool,
    db_only: bool,
    history_limit: int,
    progress_placeholder,
) -> None:
    command = [
        sys.executable,
        "-m",
        "job_search.cli",
        "run",
        "--sector",
        sector,
        "--profile",
        profile,
        "--max-offers",
        str(max_offers),
        "--match-limit",
        str(match_limit),
        "--history-limit",
        str(history_limit),
    ]
    if source != "all":
        command.extend(["--source", source])
    if not sync_vectors:
        command.append("--no-sync-vectors")
    if db_only:
        command.append("--db-only")

    st.session_state["last_command"] = " ".join(quote(part) for part in command)
    st.session_state["pipeline_running"] = True

    current_step = PIPELINE_STEPS[0]
    live_status: dict[str, int] = {
        "new": 0,
        "accepted": 0,
        "evaluated": 0,
        "errors": 0,
    }

    def _on_line(line: str) -> None:
        nonlocal current_step
        current_step = _detect_pipeline_step(line, current_step)
        partial = _status_from_output(line + "\n")
        for key in live_status:
            if partial.get(key, 0):
                live_status[key] = partial[key]
        with progress_placeholder.container():
            render_loading_steps(current_step, PIPELINE_STEPS)
            render_status_summary(live_status)

    try:
        return_code, final_output = _run_command(command, on_line=_on_line)
    except Exception:
        st.session_state["pipeline_running"] = False
        st.error("Nie udało się uruchomić wyszukiwania. Spróbuj ponownie.")
        return

    st.session_state["last_output"] = final_output
    st.session_state["last_status"] = _status_from_output(final_output)
    st.session_state["pipeline_running"] = False

    with progress_placeholder.container():
        render_loading_steps("Gotowe", PIPELINE_STEPS)
        render_status_summary(st.session_state["last_status"])

    if return_code == 0:
        st.success("Wyszukiwanie zakończone. Sprawdź rekomendacje poniżej.")
    else:
        st.error("Wyszukiwanie zakończyło się z błędami. Szczegóły w sekcji Diagnoza.")


def _hide_offer(offer_id: int, profile: str) -> None:
    command = [
        sys.executable,
        "-m",
        "job_search.cli",
        "hide-offer",
        "--offer-id",
        str(offer_id),
        "--profile",
        profile,
    ]
    st.session_state["last_command"] = " ".join(quote(part) for part in command)
    try:
        return_code, output = _run_command(command)
    except Exception:
        st.error("Nie udało się ukryć oferty.")
        return

    st.session_state["last_output"] = output
    if return_code == 0:
        st.success("Oferta została ukryta.")
        st.rerun()
    else:
        st.error("Nie udało się ukryć oferty.")


def _show_env_banner(env_exists: bool, key_present: bool) -> None:
    if env_exists and key_present:
        st.caption("System gotowy do wyszukiwania ofert.")
    else:
        missing = []
        if not env_exists:
            missing.append("plik .env")
        if not key_present:
            missing.append("klucz LLM_API_KEY")
        st.warning(f"Brakuje: {', '.join(missing)}. Dopasowanie może nie działać poprawnie.")


def _show_search_page(
    sectors: list[tuple[str, str]],
    profile_options: list[tuple[str, str]],
    db_path: Path | None,
) -> str:
    sector_options = [sector_id for sector_id, _ in sectors]
    sector_labels = {sector_id: name for sector_id, name in sectors}
    profile_map = {path: label for path, label in profile_options}

    col1, col2 = st.columns(2)
    with col1:
        selected_sector = st.selectbox(
            "Sektor",
            options=sector_options,
            format_func=lambda sector_id: sector_labels.get(sector_id, sector_id),
        )
    with col2:
        selected_profile = st.selectbox(
            "Profil",
            options=[path for path, _ in profile_options],
            format_func=lambda path: profile_map.get(path, path),
        )

    with st.expander("Ustawienia zaawansowane", expanded=False):
        source = st.selectbox("Źródło", options=["all", *SUPPORTED_SOURCES], index=0)
        max_offers = int(st.number_input("Maks. ofert", min_value=1, value=20, step=1))
        match_limit = int(st.number_input("Limit dopasowań LLM", min_value=1, value=20, step=1))
        sync_vectors = st.toggle("Synchronizuj wektory (ChromaDB)", value=True)
        db_only = st.toggle("Tylko dane z bazy (bez scrapowania)", value=False)
        history_limit = int(
            st.number_input("Historia rekomendacji w logu", min_value=0, value=10, step=1)
        )

    progress_placeholder = st.empty()

    if st.button("Szukaj ofert", type="primary", use_container_width=True):
        if _ensure_database_ready(db_path):
            with progress_placeholder.container():
                render_loading_steps(PIPELINE_STEPS[0], PIPELINE_STEPS)
            _run_pipeline(
                sector=selected_sector,
                profile=selected_profile,
                source=source,
                max_offers=max_offers,
                match_limit=match_limit,
                sync_vectors=sync_vectors,
                db_only=db_only,
                history_limit=history_limit,
                progress_placeholder=progress_placeholder,
            )

    status = st.session_state.get("last_status")
    if status:
        st.markdown("### Podsumowanie ostatniego wyszukiwania")
        render_status_summary(status)

    st.markdown("### Najnowsze rekomendacje")
    _show_recommendations_cards(db_path, sectors, selected_profile, limit=5)

    return selected_profile


def _show_recommendations_cards(
    db_path: Path | None,
    sectors: list[tuple[str, str]],
    profile_path: str,
    *,
    limit: int = 50,
) -> None:
    if not db_path or not db_path.exists():
        st.info("Brak danych. Kliknij „Szukaj ofert”, aby pobrać pierwsze wyniki.")
        return

    sector_map = {sector_id: name for sector_id, name in sectors}
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_sector = st.selectbox(
            "Sektor",
            ["all"] + [sector_id for sector_id, _ in sectors],
            format_func=lambda sid: "Wszystkie sektory"
            if sid == "all"
            else f"{sector_map.get(sid, sid)}",
            key="reco_sector",
        )
    with col2:
        selected_source = st.selectbox("Źródło", ["all", *SUPPORTED_SOURCES], key="reco_source")
    with col3:
        search_text = st.text_input("Szukaj", value="", key="reco_search", placeholder="Firma lub stanowisko")

    rows = fetch_recommendations(
        db_path,
        sector=None if selected_sector == "all" else selected_sector,
        source=None if selected_source == "all" else selected_source,
        text_query=search_text,
        limit=limit,
    )
    render_cards_from_rows(
        rows,
        sector_map,
        hide_callback=_hide_offer,
        profile_path=profile_path,
    )


def _show_profile_page() -> None:
    st.markdown("### Mój profil")
    st.caption(
        "Pobierz szablon JSON, uzupełnij swoje dane i wgraj plik. "
        "Profil zostanie zapisany lokalnie — gotowe pod przyszły hosting (AWS/Azure)."
    )

    template = load_template_dict()
    template_json = json.dumps(template, ensure_ascii=False, indent=2)
    st.download_button(
        "Pobierz przykładowy profil (JSON)",
        data=template_json,
        file_name="profile.template.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded = st.file_uploader("Wgraj swój profil JSON", type=["json"])
    if uploaded is not None:
        try:
            data = json.loads(uploaded.getvalue().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            st.error(f"Niepoprawny plik JSON: {exc}")
            return

        result = validate_profile_dict(data)
        if result.warnings:
            for warning in result.warnings:
                st.warning(warning)

        if result.errors:
            st.error("Profil wymaga poprawek:")
            for error in result.errors:
                st.markdown(f"- {error}")
            return

        assert result.profile is not None
        st.success(f"Profil poprawny: {result.profile.name}")

        with st.expander("Podgląd profilu", expanded=False):
            st.json(result.profile.model_dump(mode="json"))

        if st.button("Zapisz profil", type="primary", use_container_width=True):
            saved = save_profile(result.profile)
            st.success(f"Zapisano: {saved}")
            st.rerun()


def _show_diag_expander() -> None:
    with st.expander("Diagnoza (dla administratora)", expanded=False):
        command = st.session_state.get("last_command", "")
        output = st.session_state.get("last_output", "")
        if command:
            st.caption("Ostatnie polecenie")
            st.code(command)
        if output:
            st.text_area("Logi", output, height=300)
        else:
            st.info("Brak logów.")


def main() -> None:
    st.set_page_config(page_title="Job Search", page_icon="🔍", layout="wide")
    _default_state()

    sectors = list_sectors_for_ui()
    profiles = list_profiles_for_ui()
    db_path = database_path_from_url()
    env_exists, key_present = detect_env_status()

    with st.sidebar:
        st.title("Job Search")
        page = st.radio(
            "Menu",
            ["Szukaj ofert", "Rekomendacje", "Mój profil"],
            label_visibility="collapsed",
        )
        _show_env_banner(env_exists, key_present)

    if not sectors:
        st.error("Nie znaleziono skonfigurowanych sektorów.")
        return

    profile_options = profiles or [("config/profiles/default.json", "Domyślny profil")]

    if page == "Szukaj ofert":
        st.header("Szukaj ofert")
        st.caption("Wybierz sektor i profil — resztę wykonamy automatycznie.")
        selected_profile = _show_search_page(sectors, profile_options, db_path)
        _show_diag_expander()
    elif page == "Rekomendacje":
        st.header("Rekomendacje")
        default_profile = profile_options[0][0]
        profile_path = st.selectbox(
            "Profil (do ukrywania ofert)",
            options=[path for path, _ in profile_options],
            format_func=lambda p: dict(profile_options).get(p, p),
        )
        _show_recommendations_cards(db_path, sectors, profile_path or default_profile)
        _show_diag_expander()
    else:
        _show_profile_page()
        _show_diag_expander()


if __name__ == "__main__":
    main()
