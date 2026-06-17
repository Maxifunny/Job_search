"""Streamlit UI for non-technical demo of the job search pipeline."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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
    if "last_output" not in st.session_state:
        st.session_state["last_output"] = ""
    if "last_status" not in st.session_state:
        st.session_state["last_status"] = None


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
                    summary["scraped"] += int(part.removeprefix("found=") or 0)
                elif part.startswith("new="):
                    summary["new"] += int(part.removeprefix("new=") or 0)
                elif part.startswith("updated="):
                    summary["updated"] += int(part.removeprefix("updated=") or 0)
        if "evaluated=" in line and "accepted=" in line and "rejected=" in line:
            parts = line.split()
            for part in parts:
                if part.startswith("evaluated="):
                    summary["evaluated"] = int(part.removeprefix("evaluated=") or 0)
                elif part.startswith("accepted="):
                    summary["accepted"] = int(part.removeprefix("accepted=") or 0)
                elif part.startswith("rejected="):
                    summary["rejected"] = int(part.removeprefix("rejected=") or 0)
                elif part.startswith("skipped="):
                    summary["skipped"] = int(part.removeprefix("skipped=") or 0)
        if "Błędy" in line or "failed:" in line.lower():
            summary["errors"] += 1

    return summary


def _run_pipeline(
    *,
    sector: str,
    profile: str,
    source: str,
    max_offers: int,
    match_limit: int,
    sync_vectors: bool,
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
    ]
    if source != "all":
        command.extend(["--source", source])
    if not sync_vectors:
        command.append("--no-sync-vectors")

    st.write("### Uruchamianie pipeline")
    st.caption("Polecenie uruchamiane w tle (bez ujawniania kluczy API).")
    st.code(" ".join(command))

    output_placeholder = st.empty()
    output_lines: list[str] = []
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

    if process.stdout is not None:
        for line in process.stdout:
            output_lines.append(line.rstrip("\n"))
            output_placeholder.text("\n".join(output_lines[-400:]))

    return_code = process.wait()
    final_output = "\n".join(output_lines)
    st.session_state["last_output"] = final_output
    st.session_state["last_status"] = _status_from_output(final_output)

    if return_code == 0:
        st.success("Pipeline zakończony pomyślnie.")
    else:
        st.error(f"Pipeline zakończony błędem (kod wyjścia: {return_code}).")


def _show_status_tab(db_path: Path | None) -> None:
    status = st.session_state.get("last_status")
    if not status and db_path and db_path.exists():
        status = fetch_latest_status(db_path)
    if not status:
        st.info("Brak danych statusu. Uruchom pipeline lub upewnij się, że baza istnieje.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Zescrapowane", status["scraped"])
    col2.metric("Nowe", status["new"])
    col3.metric("Zaktualizowane", status["updated"])
    col4.metric("Błędy", status["errors"])

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Ocenione", status["evaluated"])
    col6.metric("Zaakceptowane", status["accepted"])
    col7.metric("Odrzucone", status["rejected"])
    col8.metric("Pominięte", status["skipped"])


def _show_recommendations_tab(db_path: Path | None, sectors: list[tuple[str, str]]) -> None:
    if not db_path or not db_path.exists():
        st.warning("Brak bazy SQLite. Najpierw uruchom pipeline, aby wygenerować dane.")
        return

    sector_options = ["all"] + [sector_id for sector_id, _ in sectors]
    selected_sector = st.selectbox("Filtr sektor", sector_options, index=0, key="reco_sector")
    selected_source = st.selectbox(
        "Filtr źródło", ["all", *SUPPORTED_SOURCES], index=0, key="reco_source"
    )
    search_text = st.text_input("Szukaj po tytule lub firmie", value="", key="reco_search")

    rows = fetch_recommendations(
        db_path,
        sector=None if selected_sector == "all" else selected_sector,
        source=None if selected_source == "all" else selected_source,
        text_query=search_text,
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _show_offers_tab(db_path: Path | None, sectors: list[tuple[str, str]]) -> None:
    if not db_path or not db_path.exists():
        st.warning("Brak bazy SQLite. Najpierw uruchom pipeline, aby wygenerować dane.")
        return

    sector_options = ["all"] + [sector_id for sector_id, _ in sectors]
    selected_sector = st.selectbox("Filtr sektor", sector_options, index=0, key="offers_sector")
    selected_source = st.selectbox(
        "Filtr źródło", ["all", *SUPPORTED_SOURCES], index=0, key="offers_source"
    )
    rows = fetch_offers(
        db_path,
        sector=None if selected_sector == "all" else selected_sector,
        source=None if selected_source == "all" else selected_source,
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _show_logs_tab() -> None:
    output = st.session_state.get("last_output", "")
    if not output:
        st.info("Brak logów z bieżącej sesji. Uruchom pipeline przyciskiem w panelu bocznym.")
        return
    st.text_area("STDOUT/STDERR ostatniego uruchomienia", output, height=420)


def main() -> None:
    st.set_page_config(page_title="Job Search UI", layout="wide")
    _default_state()

    st.title("Job Search — Panel demonstracyjny")
    st.caption("Prosty interfejs do uruchamiania pipeline i przeglądania wyników.")

    sectors = list_sectors_for_ui()
    profiles = list_profiles_for_ui()
    db_path = database_path_from_url()
    env_exists, key_present = detect_env_status()

    with st.sidebar:
        st.header("Ustawienia pipeline")
        if not env_exists:
            st.warning("Brak pliku `.env` w katalogu projektu.")
        if not key_present:
            st.warning("Brak `LLM_API_KEY` — matching działa w trybie ograniczonym.")

        selected_sector = st.selectbox(
            "Sektor",
            options=[sector_id for sector_id, _ in sectors],
            format_func=lambda sector_id: next(
                (f"{sid} — {name}" for sid, name in sectors if sid == sector_id), sector_id
            ),
        )
        selected_profile = st.selectbox(
            "Profil",
            options=profiles or ["config/profiles/default.json"],
        )
        selected_source = st.selectbox("Źródło", options=["all", *SUPPORTED_SOURCES], index=0)
        max_offers = st.number_input("Maks. ofert na źródło", min_value=1, value=20, step=1)
        match_limit = st.number_input("Limit ocen dopasowania", min_value=1, value=20, step=1)
        sync_vectors = st.toggle("Synchronizuj wektory (ChromaDB)", value=True)

        run_button = st.button("Uruchom pipeline", type="primary", use_container_width=True)

    if run_button:
        _run_pipeline(
            sector=selected_sector,
            profile=selected_profile,
            source=selected_source,
            max_offers=int(max_offers),
            match_limit=int(match_limit),
            sync_vectors=bool(sync_vectors),
        )

    tabs = st.tabs(["Status", "Rekomendacje", "Oferty", "Logi/Diagnoza"])
    with tabs[0]:
        _show_status_tab(db_path)
    with tabs[1]:
        _show_recommendations_tab(db_path, sectors)
    with tabs[2]:
        _show_offers_tab(db_path, sectors)
    with tabs[3]:
        _show_logs_tab()


if __name__ == "__main__":
    main()
