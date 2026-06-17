"""Streamlit UI with simple-first UX for non-technical users."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from shlex import quote

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

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


def _default_state() -> None:
    defaults = {
        "last_output": "",
        "last_status": None,
        "last_command": "",
        "db_prepared": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _run_command(command: list[str]) -> tuple[int, str]:
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
            output_lines.append(line.rstrip("\n"))
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


def _ensure_database_ready(db_path: Path | None) -> bool:
    if st.session_state.get("db_prepared"):
        return True
    if db_path is None:
        st.warning("Aktualny DATABASE_URL nie wskazuje SQLite. Pomijam automatyczne przygotowanie.")
        st.session_state["db_prepared"] = True
        return True

    try:
        with st.spinner("Przygotowuje baze danych..."):
            setup_logs: list[str] = []
            if not db_path.exists():
                init_cmd = [sys.executable, "-m", "job_search.cli", "init-db"]
                code, output = _run_command(init_cmd)
                setup_logs.append(f"$ {' '.join(quote(p) for p in init_cmd)}\n{output}".strip())
                if code != 0:
                    st.session_state["last_output"] = "\n\n".join(setup_logs)
                    st.session_state["last_command"] = " && ".join(
                        " ".join(quote(part) for part in init_cmd)
                    )
                    st.error("Nie udalo sie zainicjalizowac bazy danych.")
                    return False

            migrate_cmd = [sys.executable, "-m", "job_search.cli", "migrate"]
            code, output = _run_command(migrate_cmd)
            setup_logs.append(f"$ {' '.join(quote(p) for p in migrate_cmd)}\n{output}".strip())
            st.session_state["last_output"] = "\n\n".join(setup_logs)
            st.session_state["last_command"] = " && ".join(
                line.splitlines()[0].removeprefix("$ ") for line in setup_logs if line
            )
            if code != 0:
                st.error("Baza danych nie jest gotowa. Sprawdz zakladke Diagnoza.")
                return False
    except Exception:
        st.error("Wystapil problem podczas przygotowania bazy. Sprawdz zakladke Diagnoza.")
        return False

    st.session_state["db_prepared"] = True
    st.success("Baza danych jest gotowa.")
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
    try:
        with st.spinner("Szukam ofert i dopasowuje je do profilu..."):
            return_code, final_output = _run_command(command)
    except Exception:
        st.error("Nie udalo sie uruchomic wyszukiwania. Sprobuj ponownie.")
        return

    st.session_state["last_output"] = final_output
    st.session_state["last_status"] = _status_from_output(final_output)
    if return_code == 0:
        st.success("Wyszukiwanie zakonczone. Sprawdz zakladke Rekomendacje.")
    else:
        st.error("Nie udalo sie zakonczyc wyszukiwania poprawnie. Szczegoly sa w Diagnozie.")


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
        with st.spinner("Ukrywam oferte..."):
            return_code, output = _run_command(command)
    except Exception:
        st.error("Nie udalo sie ukryc oferty. Sprobuj ponownie.")
        return

    st.session_state["last_output"] = output
    if return_code == 0:
        st.success("Oferta zostala ukryta. Nie bedzie juz sugerowana dla tego profilu.")
    else:
        st.error("Nie udalo sie ukryc oferty. Sprawdz zakladke Diagnoza.")


def _show_env_banner(env_exists: bool, key_present: bool) -> None:
    env_text = ".env OK" if env_exists else "brak .env"
    key_text = "LLM key OK" if key_present else "LLM key: brak"
    st.info(f"Srodowisko: {env_text} | {key_text}")


def _show_status_tab(db_path: Path | None) -> None:
    status = st.session_state.get("last_status")
    if not status and db_path and db_path.exists():
        status = fetch_latest_status(db_path)
    if not status:
        st.info("Status pojawi sie po pierwszym uruchomieniu wyszukiwania.")
        return
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Zescrapowane", status["scraped"])
    col2.metric("Nowe", status["new"])
    col3.metric("Zaktualizowane", status["updated"])
    col4.metric("Bledy", status["errors"])
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Ocenione", status["evaluated"])
    col6.metric("Zaakceptowane", status["accepted"])
    col7.metric("Odrzucone", status["rejected"])
    col8.metric("Pominiete", status["skipped"])


def _show_hide_form(profile_path: str, form_key: str) -> None:
    st.markdown("### Ukryj oferte")
    with st.form(key=form_key):
        offer_id = st.number_input("ID oferty", min_value=1, step=1)
        submitted = st.form_submit_button("Ukryj oferte", use_container_width=True)
        if submitted:
            _hide_offer(int(offer_id), profile_path)


def _show_recommendations_tab(
    db_path: Path | None, sectors: list[tuple[str, str]], profile_path: str
) -> None:
    if not db_path or not db_path.exists():
        st.info("Brak danych. Kliknij 'Szukaj ofert', aby pobrac pierwsze wyniki.")
        return
    sector_map = {sector_id: name for sector_id, name in sectors}
    selected_sector = st.selectbox(
        "Sektor",
        ["all"] + [sector_id for sector_id, _ in sectors],
        format_func=lambda sid: "Wszystkie sektory"
        if sid == "all"
        else f"{sector_map.get(sid, sid)}",
        key="reco_sector",
    )
    selected_source = st.selectbox("Zrodlo", ["all", *SUPPORTED_SOURCES], key="reco_source")
    search_text = st.text_input("Szukaj po tytule lub firmie", value="", key="reco_search")
    rows = fetch_recommendations(
        db_path,
        sector=None if selected_sector == "all" else selected_sector,
        source=None if selected_source == "all" else selected_source,
        text_query=search_text,
    )
    pretty_rows = [
        {
            "ID": row.get("offer_id"),
            "Kiedy": row.get("recommended_at"),
            "Firma": row.get("company"),
            "Stanowisko": row.get("title"),
            "Sektor": sector_map.get(str(row.get("sector")), row.get("sector")),
            "Zrodlo": row.get("source"),
            "Decyzja": row.get("decision"),
            "Ocena LLM": row.get("llm_score"),
            "Ocena semantyczna": row.get("semantic_score"),
            "Link": row.get("url"),
        }
        for row in rows
    ]
    st.dataframe(pretty_rows, use_container_width=True, hide_index=True)
    _show_hide_form(profile_path, form_key="hide_reco_form")


def _show_offers_tab(db_path: Path | None, sectors: list[tuple[str, str]], profile_path: str) -> None:
    if not db_path or not db_path.exists():
        st.info("Brak ofert do wyswietlenia.")
        return
    sector_map = {sector_id: name for sector_id, name in sectors}
    selected_sector = st.selectbox(
        "Sektor ofert",
        ["all"] + [sector_id for sector_id, _ in sectors],
        format_func=lambda sid: "Wszystkie sektory"
        if sid == "all"
        else f"{sector_map.get(sid, sid)}",
        key="offers_sector",
    )
    selected_source = st.selectbox(
        "Zrodlo ofert",
        ["all", *SUPPORTED_SOURCES],
        key="offers_source",
    )
    rows = fetch_offers(
        db_path,
        sector=None if selected_sector == "all" else selected_sector,
        source=None if selected_source == "all" else selected_source,
    )
    pretty_rows = [
        {
            "ID": row.get("offer_id"),
            "Kiedy widziana": row.get("last_seen_at"),
            "Sektor": sector_map.get(str(row.get("sector")), row.get("sector")),
            "Zrodlo": row.get("source"),
            "Firma": row.get("company"),
            "Stanowisko": row.get("title"),
            "Aktywna": "tak" if row.get("is_active") else "nie",
            "Link": row.get("url"),
        }
        for row in rows
    ]
    st.dataframe(pretty_rows, use_container_width=True, hide_index=True)
    _show_hide_form(profile_path, form_key="hide_offers_form")


def _show_diag_tab() -> None:
    command = st.session_state.get("last_command", "")
    output = st.session_state.get("last_output", "")
    if command:
        st.caption("Ostatnie polecenie")
        st.code(command)
    if output:
        st.text_area("Surowe logi (STDOUT/STDERR)", output, height=440)
    else:
        st.info("Brak danych diagnostycznych.")


def main() -> None:
    st.set_page_config(page_title="Job Search UI", layout="wide")
    _default_state()

    sectors = list_sectors_for_ui()
    profiles = list_profiles_for_ui()
    db_path = database_path_from_url()
    env_exists, key_present = detect_env_status()

    st.title("Asystent wyszukiwania ofert")
    st.caption("Tryb prosty: wybierz sektor i profil, a reszte wykonamy automatycznie.")
    _show_env_banner(env_exists, key_present)

    if not sectors:
        st.error("Nie znaleziono skonfigurowanych sektorow.")
        return

    sector_options = [sector_id for sector_id, _ in sectors]
    sector_labels = {sector_id: name for sector_id, name in sectors}
    profile_options = profiles or [("config/profiles/default.json", "Domyslny profil")]
    profile_map = {path: label for path, label in profile_options}

    selected_sector = st.selectbox(
        "Sektor",
        options=sector_options,
        format_func=lambda sector_id: sector_labels.get(sector_id, sector_id),
    )
    selected_profile = st.selectbox(
        "Profil",
        options=[path for path, _ in profile_options],
        format_func=lambda path: profile_map.get(path, path),
    )

    source = "all"
    max_offers = 20
    match_limit = 20
    sync_vectors = True
    db_only = False
    history_limit = 10

    with st.expander("Ustawienia zaawansowane", expanded=False):
        source = st.selectbox("Zrodlo", options=["all", *SUPPORTED_SOURCES], index=0)
        max_offers = int(st.number_input("Maksymalna liczba ofert", min_value=1, value=20, step=1))
        match_limit = int(st.number_input("Limit dopasowan", min_value=1, value=20, step=1))
        sync_vectors = st.toggle("Synchronizuj wektory (ChromaDB)", value=True)
        db_only = st.toggle("Tylko dane z bazy (bez scrapowania)", value=False)
        history_limit = int(
            st.number_input("Liczba historycznych rekomendacji", min_value=0, value=10, step=1)
        )

    run_button = st.button("Szukaj ofert", type="primary", use_container_width=True)
    if run_button:
        if _ensure_database_ready(db_path):
            _run_pipeline(
                sector=selected_sector,
                profile=selected_profile,
                source=source,
                max_offers=max_offers,
                match_limit=match_limit,
                sync_vectors=sync_vectors,
                db_only=db_only,
                history_limit=history_limit,
            )

    tabs = st.tabs(["Rekomendacje", "Status", "Oferty", "Diagnoza"])
    with tabs[0]:
        _show_recommendations_tab(db_path, sectors, selected_profile)
    with tabs[1]:
        _show_status_tab(db_path)
    with tabs[2]:
        _show_offers_tab(db_path, sectors, selected_profile)
    with tabs[3]:
        _show_diag_tab()


if __name__ == "__main__":
    main()
