"""Email body templates for job recommendations."""

from __future__ import annotations

from dataclasses import dataclass

from job_search.notifications.tokens import create_confirm_token


@dataclass(frozen=True)
class EmailOfferItem:
    offer_id: int
    title: str
    company: str
    url: str
    source: str
    recommended_at: str
    llm_score: float | None
    confirm_token: str
    confirm_command: str


@dataclass(frozen=True)
class EmailDigest:
    subject: str
    text_body: str
    html_body: str


def build_confirm_command(candidate_name: str, offer_id: int) -> str:
    return (
        f"python -m job_search.cli notify mark-applied "
        f"--profile config/profiles/{candidate_name}.json --offer-id {offer_id}"
    )


def build_digest(
    *,
    candidate_name: str,
    offers: list[dict],
    secret: str,
    public_base_url: str = "",
) -> EmailDigest:
    items: list[EmailOfferItem] = []
    for index, row in enumerate(offers, start=1):
        offer_id = int(row["offer_id"])
        token = create_confirm_token(
            candidate_name=candidate_name,
            job_offer_id=offer_id,
            secret=secret,
        )
        confirm_command = build_confirm_command(candidate_name, offer_id)
        token_command = f"python -m job_search.cli notify confirm --token {token}"
        if public_base_url:
            confirm_link = f"{public_base_url.rstrip('/')}/notify/confirm?token={token}"
        else:
            confirm_link = ""

        items.append(
            EmailOfferItem(
                offer_id=offer_id,
                title=str(row["title"]),
                company=str(row["company"]),
                url=str(row["url"]),
                source=str(row.get("source", "")),
                recommended_at=str(row.get("recommended_at", "")),
                llm_score=row.get("llm_score"),
                confirm_token=token,
                confirm_command=token_command if not confirm_link else confirm_link,
            )
        )

    count = len(items)
    subject = f"Job Search: {count} nowych rekomendacji ofert pracy"

    text_lines = [
        "Cześć!",
        "",
        f"Oto {count} najnowszych rekomendacji dopasowanych do profilu '{candidate_name}':",
        "",
    ]
    html_parts = [
        "<html><body>",
        "<p>Cześć!</p>",
        f"<p>Oto <strong>{count}</strong> najnowszych rekomendacji "
        f"dla profilu <em>{candidate_name}</em>:</p>",
        "<ol>",
    ]

    for item in items:
        score_text = (
            f" (dopasowanie: {item.llm_score:.0%})" if item.llm_score is not None else ""
        )
        text_lines.extend(
            [
                f"{item.offer_id}. {item.title} @ {item.company}{score_text}",
                f"   Link: {item.url}",
                "   Zaaplikowałem — potwierdź (nie wysyłaj ponownie):",
                f"   {item.confirm_command}",
                "",
            ]
        )
        link_html = (
            f'<a href="{item.confirm_command}">Oznacz jako zaaplikowane</a>'
            if item.confirm_command.startswith("http")
            else f"<code>{item.confirm_command}</code>"
        )
        html_parts.append(
            "<li>"
            f"<strong>{item.title}</strong> @ {item.company}{score_text}<br>"
            f'<a href="{item.url}">Zobacz ofertę</a><br>'
            f"{link_html}"
            "</li>"
        )

    text_lines.extend(
        [
            "Alternatywnie (CLI):",
            "  python -m job_search.cli notify mark-applied --profile <profil.json> --offer-id <ID>",
            "",
            "— Job Search Notifier",
        ]
    )
    html_parts.extend(
        [
            "</ol>",
            "<p><small>Alternatywnie: "
            "<code>python -m job_search.cli notify mark-applied --profile ... --offer-id ...</code>"
            "</small></p>",
            "<p>— Job Search Notifier</p>",
            "</body></html>",
        ]
    )

    return EmailDigest(
        subject=subject,
        text_body="\n".join(text_lines),
        html_body="\n".join(html_parts),
    )
