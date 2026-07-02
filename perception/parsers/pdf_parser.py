"""Parseur PDF texte - factures natives (T-M06-1).

Extrait le texte d'un PDF **textuel** (pas un scan) avec la bibliotheque
standard uniquement : les flux de contenu sont decompresses (FlateDecode
via ``zlib``) et les operateurs texte ``Tj``/``TJ`` sont decodes. Les
champs metier (montant, date, fournisseur) sont ensuite extraits en
appliquant des **regles d'extraction versionnees** (famille
``extraction/*`` du corpus de regles, T-M02-1) - des motifs declares,
jamais un texte devine.

Regle anti-invention : un champ introuvable ou illisible n'est **jamais**
invente - il est absent du resultat et produit une anomalie « champ
illisible » avec demande de saisie manuelle (le mode manuel est le mode
officiel). Un PDF sans texte extractible (scan/image) produit la meme
anomalie pour tous les champs.
"""
import json
import os
import re
import zlib
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store, rules
from core.envelope import make_envelope

EXTRACTION_RULE_NAME = "extraction/facture-pdf"
DEFAULT_AUTHOR = "agent:perception"

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_TEXT_SHOW_RE = re.compile(rb"\((?:\\.|[^()\\])*\)\s*Tj|\[(?:[^\]]*)\]\s*TJ")
_PAREN_RE = re.compile(rb"\((?:\\.|[^()\\])*\)")


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_pdf_string(raw):
    """Decode une chaine PDF entre parentheses (echappements \\n \\( \\) \\\\)."""
    body = raw[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        byte = body[i]
        if byte == 0x5C and i + 1 < len(body):  # backslash
            nxt = body[i + 1]
            mapping = {0x6E: 0x0A, 0x72: 0x0D, 0x74: 0x09, 0x28: 0x28, 0x29: 0x29, 0x5C: 0x5C}
            out.append(mapping.get(nxt, nxt))
            i += 2
        else:
            out.append(byte)
            i += 1
    return out.decode("latin-1", errors="replace")


def extract_text(path):
    """Texte brut d'un PDF textuel : concatene les chaines des operateurs
    ``Tj``/``TJ`` de chaque flux de contenu (decompresse si FlateDecode).
    Renvoie une chaine vide si aucun texte n'est extractible - jamais un
    texte invente."""
    with open(path, "rb") as handle:
        raw = handle.read()

    pieces = []
    for match in _STREAM_RE.finditer(raw):
        stream = match.group(1)
        try:
            stream = zlib.decompress(stream)
        except zlib.error:
            pass  # flux non compresse : on le lit tel quel
        for op in _TEXT_SHOW_RE.finditer(stream):
            # Un operateur Tj/TJ = un segment de texte positionne : on le
            # restitue comme une ligne pour permettre une extraction par
            # motifs ligne-a-ligne (les factures sont des documents lignes).
            pieces.append("".join(
                _decode_pdf_string(literal.group(0))
                for literal in _PAREN_RE.finditer(op.group(0))
            ))
    return "\n".join(pieces)


def _apply_extraction_rule(text, rule_body):
    """Applique les motifs declares par la regle d'extraction : pour
    chaque champ, le premier groupe capturant du premier motif qui matche.
    Champ sans match -> absent (jamais une valeur inventee)."""
    extracted = {}
    for field, patterns in rule_body["fields"].items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                extracted[field] = match.group(1).strip()
                break
    return extracted


def _manual_entry_anomaly(conn, path, missing_fields, event_id):
    now = _now_iso()
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                               recommendation, state, created_at, refs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly_id, "perception/champ-illisible", "moyenne", 1.0, None,
         f"Champ(s) illisible(s) dans la facture PDF : {', '.join(missing_fields)}. "
         "Saisir la valeur manuellement (formulaire facture).",
         "ouverte", now,
         json.dumps({"file": os.path.basename(path), "missing": missing_fields,
                     "event_id": event_id}, ensure_ascii=False)),
    )
    conn.commit()
    return anomaly_id


def parse(conn, path, at_date=None):
    """Extrait montant/date/fournisseur d'une facture PDF texte.

    Applique la regle d'extraction versionnee applicable a ``at_date``
    (``extraction/facture-pdf``). Les champs trouves deviennent un
    evenement ``PERCEPTION.InvoiceReceived`` (nature=mesure : extrait d'un
    document, pas observe directement) ; chaque champ attendu manquant
    produit une anomalie avec demande de saisie manuelle.

    Returns:
        dict: ``{"status": "parsed", "fields": {...}, "missing": [...],
        "event_id": ..., "anomaly_id": ...|None, "rule": name@version}``.
    """
    at_date = at_date or _now_iso()
    extraction_rule = rules.get(conn, EXTRACTION_RULE_NAME, at_date)
    if extraction_rule is None:
        raise LookupError(
            f"regle d'extraction absente : {EXTRACTION_RULE_NAME} (seed non chargee ?)"
        )

    text = extract_text(path)
    fields = _apply_extraction_rule(text, extraction_rule["body"])
    expected = list(extraction_rule["body"]["fields"].keys())
    missing = [field for field in expected if field not in fields]

    now = _now_iso()
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="PERCEPTION.InvoiceReceived",
        label=f"Facture PDF : {os.path.basename(path)}",
        source=f"inbox/{os.path.basename(path)}",
        author=DEFAULT_AUTHOR,
        valid_from=now,
        ts_record=now,
        nature="mesuré",
        score=0.9 if not missing else 0.5,
        owner="system",
        visibility="interne",
        authority=1,
    )
    _, event_id = event_store.append(
        conn, envelope,
        payload={"fields": fields, "missing": missing,
                 "rule": f"{extraction_rule['name']}@{extraction_rule['version']}",
                 "file": os.path.basename(path)},
        rule_version_ref=f"{extraction_rule['name']}@{extraction_rule['version']}",
    )

    anomaly_id = _manual_entry_anomaly(conn, path, missing, event_id) if missing else None

    return {"status": "parsed", "fields": fields, "missing": missing,
            "event_id": event_id, "anomaly_id": anomaly_id,
            "rule": f"{extraction_rule['name']}@{extraction_rule['version']}"}
