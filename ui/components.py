"""Reusable Streamlit UI components."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_offer_card(
    *,
    title: str,
    company: str,
    url: str,
    source: str | None = None,
    sector_label: str | None = None,
    score: float | None = None,
    offer_id: int | None = None,
    hide_callback=None,
    profile_path: str | None = None,
) -> None:
    """Render a single client-friendly offer card."""
    with st.container(border=True):
        cols = st.columns([4, 1])
        with cols[0]:
            st.markdown(f"### {title}")
            st.markdown(f"**{company}**")
            meta = []
            if sector_label:
                meta.append(sector_label)
            if source:
                meta.append(source)
            if meta:
                st.caption(" · ".join(meta))
            if score is not None:
                st.progress(min(max(float(score), 0.0), 1.0), text=f"Dopasowanie: {score:.0%}")
            st.link_button("Zobacz ofertę", url, use_container_width=False)
        with cols[1]:
            if offer_id is not None and hide_callback and profile_path:
                if st.button("Ukryj", key=f"hide_{offer_id}_{title[:20]}", use_container_width=True):
                    hide_callback(offer_id, profile_path)


def render_status_summary(status: dict[str, int]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nowe oferty", status.get("new", 0))
    col2.metric("Dopasowane", status.get("accepted", 0))
    col3.metric("Ocenione", status.get("evaluated", 0))
    col4.metric("Błędy", status.get("errors", 0))


def render_loading_steps(current_step: str, steps: list[str]) -> None:
    st.markdown("#### Postęp")
    for step in steps:
        if step == current_step:
            st.markdown(f"- **{step}**")
        else:
            st.markdown(f"- {step}")


def render_cards_from_rows(rows: list[dict[str, Any]], sector_map: dict[str, str], **kwargs) -> None:
    if not rows:
        st.info("Brak wyników do wyświetlenia.")
        return
    for row in rows:
        render_offer_card(
            title=str(row.get("title", "Oferta")),
            company=str(row.get("company", "")),
            url=str(row.get("url", "#")),
            source=str(row.get("source", "")) if row.get("source") else None,
            sector_label=sector_map.get(str(row.get("sector")), str(row.get("sector", ""))),
            score=row.get("llm_score") or row.get("semantic_score"),
            offer_id=row.get("offer_id"),
            **kwargs,
        )
