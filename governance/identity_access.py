"""Identite & acces - journal d'acces (T-M29-1).

Toute operation sensible laisse une trace **qui / quoi / quand** dans la
table ``access_log`` (creee par le schema fige T-M00-1) : saisie
manuelle, confirmation OCR, attribution d'autorite, refus de permission,
consultation d'une preuve... (Constitution, loi 17 : « tout est
journalise » ; section VII : « accès sans trace » est interdit).

Le journal d'acces est une trace operationnelle (projection) ; la piste
d'audit de la verite metier reste le journal d'evenements (M01).
"""
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_access(conn, subject, action, target, ts=None):
    """Trace un acces/une action sensible.

    Args:
        conn: connexion SQLite ouverte.
        subject: qui (``"human:pierre"``, ``"agent:perception"``...).
        action: quoi (``"manual-entry"``, ``"ocr-confirm"``,
            ``"permission-denied"``...).
        target: sur quoi (identifiant d'objet/evenement/formulaire).
        ts: quand (defaut : maintenant, UTC).

    Returns:
        str: l'horodatage enregistre.
    """
    ts = ts or _now_iso()
    conn.execute(
        "INSERT INTO access_log (ts, subject, action, target) VALUES (?, ?, ?, ?)",
        (ts, subject, action, target),
    )
    conn.commit()
    return ts


def recent(conn, limit=50, subject=None, action=None):
    """Relit les traces d'acces, les plus recentes d'abord (filtrables
    par sujet et/ou action)."""
    clauses, params = [], []
    if subject is not None:
        clauses.append("subject = ?")
        params.append(subject)
    if action is not None:
        clauses.append("action = ?")
        params.append(action)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT ts, subject, action, target FROM access_log {where} "
        f"ORDER BY ts DESC LIMIT ?", params + [limit],
    ).fetchall()
    return [{"ts": r[0], "subject": r[1], "action": r[2], "target": r[3]} for r in rows]
