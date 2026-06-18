# Notifier Agent — Email digest

**Branch:** `cursor/notifier-email-503f`  
**Moduły:** `src/job_search/notifications/`, migracja `004_notification_log`, `cli notify`

---

## Cel

Wysyłka **emailowych podsumowań** z maksymalnie **10 najnowszymi** rekomendacjami oraz mechanizm **potwierdzenia „zaaplikowałem”**, żeby te oferty nie wracały w kolejnych mailach.

Notifier jest **wbudowany** w pipeline (`NOTIFIER_ENABLED=true`) i działa też **osobno** przez CLI.

> Instrukcja wdrożenia AWS (EC2, cron raz dziennie, SES): [aws-deployment-agent.md](aws-deployment-agent.md)

---

## Architektura

```
MATCH → RECOMMEND → NOTIFY (email)
                         │
                         ├─ wybierz max 10 najnowszych rekomendacji
                         ├─ pomiń: applied, hidden, już wysłane (notification_log)
                         ├─ wyślij SMTP (text + HTML)
                         └─ każda oferta ma token / komendę confirm
```

### Tabele

| Tabela | Rola |
|--------|------|
| `recommendations.user_action` | `applied` = użytkownik zaaplikował |
| `notification_log` | oferta już wysłana mailem (nie wysyłaj ponownie) |
| `hidden_offers` | ustawiane przy `mark-applied` (reason: applied) |

---

## Konfiguracja `.env`

```env
NOTIFIER_ENABLED=true
NOTIFIER_MAX_OFFERS=10
NOTIFIER_SECRET=twoj-losowy-sekret-min-16-znakow

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=twoj@gmail.com
SMTP_PASSWORD=haslo-aplikacji
SMTP_FROM=twoj@gmail.com
SMTP_TO=twoj@gmail.com
SMTP_USE_TLS=true
```

**Gmail:** użyj [hasła aplikacji](https://myaccount.google.com/apppasswords), nie zwykłego hasła.

---

## CLI

### Wyślij digest ręcznie

```powershell
python -m job_search.cli notify send --profile config/profiles/default.json
```

Opcje:
- `--limit 5` — mniej ofert w mailu
- `--dry-run` — zbuduj temat/treść bez wysyłki SMTP

### Potwierdź aplikację (z maila)

Skopiuj token z maila:

```powershell
python -m job_search.cli notify confirm --token <TOKEN_Z_MAILA>
```

### Oznacz ręcznie po ID oferty

```powershell
python -m job_search.cli notify mark-applied --profile config/profiles/default.json --offer-id 123
```

ID oferty widać w UI (karty), w bazie lub w treści maila.

---

## Integracja z pipeline

Gdy `NOTIFIER_ENABLED=true`, po matchingu:

```powershell
python -m job_search.cli run --sector data --profile config/profiles/default.json
```

Na końcu:
```
[pipeline] Email wysłany: 3 ofert → user@example.com
```

---

## Logika wyboru ofert do maila

1. Sortowanie: `recommended_at DESC`
2. Limit: `NOTIFIER_MAX_OFFERS` (domyślnie 10)
3. Wykluczenia:
   - `user_action = applied`
   - wpis w `hidden_offers`
   - wpis w `notification_log` (channel=email)

---

## Treść maila

Każda oferta zawiera:
- tytuł, firma, link
- opcjonalnie score dopasowania
- komendę: `notify confirm --token ...`
- alternatywę: `notify mark-applied --offer-id ...`

Gdy ustawisz `NOTIFIER_PUBLIC_BASE_URL` (przyszły AWS API Gateway), w mailu pojawią się klikalne linki.

---

## Testy

```bash
pytest tests/test_notifications.py -v
python -m job_search.cli migrate
```

---

## Definition of Done

- [x] Moduł `notifications/` (email, tokens, templates, service)
- [x] Migracja `notification_log`
- [x] CLI: `notify send`, `notify confirm`, `notify mark-applied`
- [x] Integracja z pipeline (`NOTIFIER_ENABLED`)
- [x] Testy jednostkowe
- [ ] AWS deployment guide — **następny agent**

---

## Następny agent: AWS

Zrealizowane w [docs/agents/aws-deployment-agent.md](aws-deployment-agent.md) — EC2 + **cron raz dziennie** (cały pipeline).
