"""Parseur CSV generique + profils source (T-M05-2).

**Aucune API : l'export CSV envoye par email/depose est le mode
officiel** (Backlog, contrainte n.2/4). Un « profil » decrit le mapping
colonnes -> champs ; les profils vivent dans
``data/source_profiles.json`` et sont verses dans le corpus de regles
(famille ``source-profile/*``, regles versionnees bi-temporelles,
T-M02-1) - changer un mapping = nouvelle version, jamais d'ecrasement.

Regle anti-invention : **un CSV sans profil n'est jamais interprete** -
aucun mapping devine, une anomalie « profil manquant » est creee et le
fichier attend une saisie/un profil humain.
"""
import csv
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from core import rules
from perception import intake_folder, quality

PROFILE_RULE_PREFIX = "source-profile/"
DEFAULT_PROFILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "source_profiles.json",
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_profiles_as_rules(conn, path=DEFAULT_PROFILES_PATH):
    """Verse chaque profil de ``source_profiles.json`` dans le corpus de
    regles (famille ``source-profile/*``), version 1, origin="seed".

    Idempotent : un profil qui possede deja une version n'est jamais
    reseede (meme garantie que ``rules.load_seed_rules``).
    """
    with open(path, "r", encoding="utf-8") as handle:
        entries = json.load(handle)

    inserted = []
    for entry in entries:
        name = PROFILE_RULE_PREFIX + entry["name"]
        if rules.get(conn, name, _now_iso()) is not None:
            continue
        inserted.append(rules.add_version(
            conn, name=name, body=entry["body"],
            valid_from=entry.get("valid_from", "2020-01-01T00:00:00Z"),
            origin="seed", note=entry.get("note"),
        ))
    return inserted


def find_profile(conn, filename, at_date=None):
    """Cherche le profil applicable a ``filename`` parmi les regles
    ``source-profile/*`` actives a ``at_date`` (le nom du fichier doit
    contenir le motif ``match`` du profil). ``None`` si aucun ne
    correspond - jamais un profil devine."""
    at_date = at_date or _now_iso()
    names = [row[0] for row in conn.execute(
        "SELECT DISTINCT name FROM rules WHERE name LIKE ?", (PROFILE_RULE_PREFIX + "%",)
    ).fetchall()]

    for name in sorted(names):
        profile_rule = rules.get(conn, name, at_date)
        if profile_rule is None:
            continue
        match = profile_rule["body"].get("match", "")
        if match and match.lower() in os.path.basename(filename).lower():
            return profile_rule
    return None


def missing_profile_anomaly(conn, path, reason="profil manquant"):
    """Anomalie « profil manquant » : le fichier n'est jamais interprete."""
    now = _now_iso()
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                               recommendation, state, created_at, refs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly_id, "perception/profil-manquant", "moyenne", 1.0, None,
         "Creer un profil source (regle source-profile/*) decrivant le mapping "
         "colonnes->champs, puis redeposer le fichier.",
         "ouverte", now,
         json.dumps({"file": os.path.basename(path), "reason": reason},
                    ensure_ascii=False)),
    )
    conn.commit()
    return anomaly_id


def read_rows(path, profile_body):
    """Lit le CSV et renvoie les enregistrements bruts mappes selon le
    profil (``mapping``: {colonne source -> champ cible}). Lecture pure :
    aucune ecriture, aucune interpretation au-dela du mapping declare."""
    delimiter = profile_body.get("delimiter", ",")
    encoding = profile_body.get("encoding", "utf-8")
    mapping = profile_body["mapping"]

    records = []
    with open(path, "r", encoding=encoding, newline="") as handle:
        for row in csv.DictReader(handle, delimiter=delimiter):
            record = {target: row.get(source_col) for source_col, target in mapping.items()}
            records.append(record)
    return records


def ingest_records(conn, path, profile, records):
    """Tronc commun CSV/XLSX : validation qualite (M07) ligne a ligne,
    quarantaine des invalides, emballage des valides en evenements par
    M04 (``intake_folder.normalize_records``), dedup par empreinte de
    ligne (M08)."""
    body = profile["body"]
    valid_records, quarantined = [], []
    for record in records:
        verdict = quality.validate(record, body.get("quality", {}))
        if verdict["valid"]:
            valid_records.append(record)
        else:
            event_id, anomaly_id = quality.quarantine(
                conn, record, verdict["errors"], source=f"inbox/{os.path.basename(path)}"
            )
            quarantined.append({"event_id": event_id, "anomaly_id": anomaly_id})

    outcome = intake_folder.normalize_records(
        conn, valid_records,
        event_type=body.get("event_type", "PERCEPTION.StatementLine"),
        source=f"inbox/{os.path.basename(path)}",
        keycols=body.get("keycols", sorted({field for field in body["mapping"].values()})),
        valid_from_field=body.get("valid_from_field"),
    )

    return {
        "status": "parsed",
        "profile": f"{profile['name']}@{profile['version']}",
        "records": len(records),
        "appended": outcome["appended"],
        "duplicates": outcome["duplicates"],
        "quarantined": quarantined,
    }


def parse(conn, path, profile=None):
    """Integre un export CSV depose.

    Args:
        conn: connexion SQLite ouverte.
        path: chemin du fichier CSV.
        profile: regle-profil (dict tel que renvoye par ``rules.get``) ou
            ``None``. Sans profil (ni fourni, ni trouve par
            ``find_profile``), le fichier n'est **jamais** interprete :
            anomalie « profil manquant ».

    Returns:
        dict: ``{"status": "no_profile", "anomaly_id": ...}`` ou
        ``{"status": "parsed", "profile": name@version, "records": n,
        "appended": [...], "duplicates": n, "quarantined": [...]}``.
    """
    if profile is None:
        profile = find_profile(conn, path)
    if profile is None:
        anomaly_id = missing_profile_anomaly(conn, path)
        return {"status": "no_profile", "anomaly_id": anomaly_id}

    records = read_rows(path, profile["body"])
    return ingest_records(conn, path, profile, records)
