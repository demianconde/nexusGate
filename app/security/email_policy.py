"""Política de e-mail no cadastro: bloqueia domínios de e-mail descartável.

Anti-abuso do plano grátis (Sybil): impedir que a mesma pessoa crie contas em
massa usando serviços de e-mail temporário/descartável (mailinator, temp-mail…).
O e-mail verificado do Supabase garante que a pessoa *possui* a caixa; esta camada
garante que a caixa não é de um provedor descartável.

A blocklist é um conjunto estático (curado) + domínios extras vindos do ambiente
(``AEGIS_DISPOSABLE_EMAIL_DOMAINS``). A checagem é determinística (não usa Redis).
"""

from __future__ import annotations

# Domínios descartáveis comuns. Não é exaustivo (existem milhares), mas cobre os
# serviços mais usados em abuso de cadastro. Extensível via config sem novo deploy.
_BUILTIN_DISPOSABLE_DOMAINS: frozenset[str] = frozenset(
    {
        "0-mail.com",
        "10minutemail.com",
        "20minutemail.com",
        "33mail.com",
        "anonbox.net",
        "anonymbox.com",
        "burnermail.io",
        "cock.li",
        "dispostable.com",
        "dropmail.me",
        "email-temp.com",
        "emailondeck.com",
        "fakeinbox.com",
        "fakemail.net",
        "gettempmail.com",
        "getnada.com",
        "guerrillamail.com",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamailblock.com",
        "harakirimail.com",
        "inboxbear.com",
        "inboxkitten.com",
        "jetable.org",
        "mailcatch.com",
        "maildrop.cc",
        "mailester.com",
        "mailinator.com",
        "mailnesia.com",
        "mailsac.com",
        "mailtemp.info",
        "moakt.com",
        "mohmal.com",
        "mytemp.email",
        "nada.email",
        "nowmymail.com",
        "sharklasers.com",
        "spam4.me",
        "spamgourmet.com",
        "temp-mail.io",
        "temp-mail.org",
        "tempail.com",
        "tempinbox.com",
        "tempmail.com",
        "tempmail.dev",
        "tempmail.plus",
        "tempmailo.com",
        "tempr.email",
        "throwawaymail.com",
        "trashmail.com",
        "trashmail.de",
        "trashmail.net",
        "tuta.io",
        "vomoto.com",
        "wegwerfmail.de",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
    }
)


def email_domain(email: str) -> str:
    """Extrai o domínio (parte após o ``@``), normalizado em minúsculas.

    Retorna string vazia se o e-mail não tiver formato ``local@domínio``.
    """
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return ""
    domain = email.rsplit("@", 1)[1].strip()
    return domain


def is_disposable_email(email: str, extra_domains: frozenset[str] | set[str] = frozenset()) -> bool:
    """True se o domínio do e-mail estiver na blocklist (built-in + ``extra_domains``).

    Um e-mail sem domínio válido é tratado como descartável (bloqueia por precaução).
    """
    domain = email_domain(email)
    if not domain:
        return True
    return domain in _BUILTIN_DISPOSABLE_DOMAINS or domain in extra_domains
