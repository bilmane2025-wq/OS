"""Moteur de graphe - Objets + Liens par repli du journal (T-M09-1,
T-M09-2).

Le graphe est une **projection reconstructible** (Conception 3.5) : il ne
detient jamais la verite (seul le journal la detient), il la materialise.
``apply(conn, event)`` replie un evenement en Objets et Liens ;
``rebuild(conn)`` reconstruit tout le graphe depuis zero en rejouant le
journal - et doit produire un etat strictement identique (invariant
teste).

Identite des Objets : pour que la reconstruction depuis zero produise le
meme etat, les identifiants d'Objets sont **derives deterministiquement
de leur cle naturelle** (SHA-256 -> sequence decimale), au format
``TYPE:ENTITE:sequence`` de M03. Deux rejeux du meme journal produisent
donc exactement les memes identifiants - condition de l'invariant de
reconstruction (Backlog T-M09-1 : "reconstruction depuis zero = etat
identique").

Frontiere M09 : le graphe n'est jamais ecrit sans evenement - toutes les
fonctions d'ecriture de ce module prennent l'evenement source en
parametre et le tracent dans l'enveloppe de l'Objet/du Lien.
"""
import hashlib
import json
from datetime import datetime, timezone

from core.envelope import make_envelope

ENTITY = "EOS"


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def object_id_for(type_, natural_key):
    """Identifiant deterministe d'un Objet : derive de (type, cle
    naturelle), stable a travers tout rejeu du journal."""
    digest = hashlib.sha256(f"{type_}|{natural_key}".encode("utf-8")).hexdigest()
    return f"{type_.upper()}:{ENTITY}:{int(digest[:12], 16)}"


def link_id_for(src, rel, dst):
    digest = hashlib.sha256(f"{src}|{rel}|{dst}".encode("utf-8")).hexdigest()
    return f"LNK:{ENTITY}:{int(digest[:12], 16)}"


def _row_hash(body, label, state):
    canonical = json.dumps({"body": body, "label": label, "state": state},
                           sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upsert_object(conn, type_, natural_key, label, body, event, state="actif",
                  nature="fait", score=1.0):
    """Cree ou met a jour un Objet de la projection (idempotent par
    ``row_hash`` : re-appliquer le meme evenement ne change rien).

    L'enveloppe de l'Objet trace l'evenement createur (provenance) - le
    graphe n'est jamais ecrit sans evenement.
    """
    object_id = object_id_for(type_, natural_key)

    existing = conn.execute(
        "SELECT row_hash, version, body_json FROM objects WHERE object_id = ?", (object_id,)
    ).fetchone()

    if existing is not None:
        # Fusion additive : un nouvel evenement enrichit le corps de
        # l'Objet, il n'efface jamais un champ deja connu (une facture qui
        # cite "Foodex" sans son role ne fait pas oublier que Foodex est
        # fournisseur). Rend le repli idempotent : rejouer la meme
        # sequence d'evenements ne change plus rien.
        body = {**json.loads(existing[2]), **body}

    row_hash = _row_hash(body, label, state)
    if existing is not None and existing[0] == row_hash:
        return object_id  # idempotence : rien a faire

    version = 1 if existing is None else existing[1] + 1
    envelope = make_envelope(
        id=object_id,
        type_=type_,
        label=label,
        source=event["source"] or "journal",
        author=event["author"] or "system:graph",
        valid_from=event["valid_from"],
        ts_record=event["ts_record"],
        nature=nature,
        score=score,
        owner="system",
        visibility="interne",
        authority=1,
        event_id=event["event_id"],
        version=version,
        state=state,
    )

    if existing is None:
        conn.execute(
            """
            INSERT INTO objects (object_id, type, label, envelope_json, body_json,
                                 state, valid_from, valid_to, ts_record, version, row_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (object_id, type_, label, json.dumps(envelope, ensure_ascii=False),
             json.dumps(body, ensure_ascii=False, default=str), state,
             event["valid_from"], event["ts_record"], version, row_hash),
        )
    else:
        # Le graphe est une projection : la nouvelle version remplace la
        # ligne courante (la verite - toutes les versions - reste dans le
        # journal, reconstructible par rejeu/state_as_of).
        conn.execute(
            """
            UPDATE objects SET label = ?, envelope_json = ?, body_json = ?, state = ?,
                               valid_from = ?, ts_record = ?, version = ?, row_hash = ?
            WHERE object_id = ?
            """,
            (label, json.dumps(envelope, ensure_ascii=False),
             json.dumps(body, ensure_ascii=False, default=str), state,
             event["valid_from"], event["ts_record"], version, row_hash, object_id),
        )
    conn.commit()
    return object_id


def upsert_link(conn, src, rel, dst, event, weight=1.0):
    """Cree un Lien (idempotent : le meme triplet src/rel/dst n'est
    jamais duplique). Un Lien est un Objet (Conception 3.2) : il porte
    lui aussi une enveloppe complete."""
    link_id = link_id_for(src, rel, dst)
    existing = conn.execute("SELECT 1 FROM links WHERE link_id = ?", (link_id,)).fetchone()
    if existing is not None:
        return link_id

    envelope = make_envelope(
        id=link_id,
        type_="Lien",
        label=f"{src} -{rel}-> {dst}",
        source=event["source"] or "journal",
        author=event["author"] or "system:graph",
        valid_from=event["valid_from"],
        ts_record=event["ts_record"],
        nature="fait",
        score=1.0,
        owner="system",
        visibility="interne",
        authority=1,
        event_id=event["event_id"],
    )
    conn.execute(
        """
        INSERT INTO links (link_id, src, rel, dst, weight, envelope_json,
                           valid_from, valid_to, ts_record, version)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)
        """,
        (link_id, src, rel, dst, weight, json.dumps(envelope, ensure_ascii=False),
         event["valid_from"], event["ts_record"]),
    )
    conn.commit()
    return link_id


def _fields_of(payload):
    """Champs metier d'un payload, quel que soit le parseur d'origine
    (PDF: 'fields', CSV/XLSX: 'record', formulaire: 'fields', direct)."""
    for key in ("fields", "record"):
        if isinstance(payload.get(key), dict):
            return payload[key]
    return payload


def _apply_invoice(conn, event, fields):
    invoice_id = upsert_object(
        conn, "Facture", f"facture:{event['event_id']}",
        label=f"Facture {fields.get('fournisseur') or ''}".strip() or "Facture",
        body=fields, event=event,
        nature=event["envelope"]["confidence"]["nature"],
        score=event["envelope"]["confidence"]["score"],
    )
    created = [invoice_id]
    supplier = fields.get("fournisseur")
    if supplier:
        supplier_id = upsert_object(
            conn, "Acteur", f"acteur:{str(supplier).strip().lower()}",
            label=str(supplier).strip(), body={"nom": str(supplier).strip(), "role": "fournisseur"},
            event=event,
        )
        upsert_link(conn, invoice_id, "concerne", supplier_id, event)
        created.append(supplier_id)
    account = fields.get("compte")
    if account:
        account_id = upsert_object(
            conn, "Compte", f"compte:{str(account).strip().lower()}",
            label=str(account).strip(), body={"numero": str(account).strip()}, event=event,
        )
        upsert_link(conn, invoice_id, "impacte", account_id, event)
        created.append(account_id)
    return created


def _apply_statement_line(conn, event, fields):
    transaction_id = upsert_object(
        conn, "Transaction", f"transaction:{event['event_id']}",
        label=fields.get("libelle") or "Transaction bancaire",
        body=fields, event=event,
        nature=event["envelope"]["confidence"]["nature"],
        score=event["envelope"]["confidence"]["score"],
    )
    created = [transaction_id]
    counterparty = fields.get("contrepartie")
    if counterparty:
        actor_id = upsert_object(
            conn, "Acteur", f"acteur:{str(counterparty).strip().lower()}",
            label=str(counterparty).strip(), body={"nom": str(counterparty).strip()}, event=event,
        )
        upsert_link(conn, transaction_id, "concerne", actor_id, event)
        created.append(actor_id)
    account_id = upsert_object(
        conn, "Compte", f"compte:{str(fields.get('compte') or 'banque-principale').lower()}",
        label=str(fields.get("compte") or "Compte bancaire principal"),
        body={"numero": str(fields.get("compte") or "banque-principale")}, event=event,
    )
    upsert_link(conn, transaction_id, "impacte", account_id, event)
    created.append(account_id)
    return created


def _apply_order(conn, event, fields):
    order_id = upsert_object(
        conn, "Commande", f"commande:{fields.get('commande_id') or event['event_id']}",
        label=f"Commande {fields.get('commande_id') or ''}".strip(),
        body=fields, event=event,
        nature=event["envelope"]["confidence"]["nature"],
        score=event["envelope"]["confidence"]["score"],
    )
    created = [order_id]
    platform = fields.get("plateforme")
    if platform:
        platform_id = upsert_object(
            conn, "Acteur", f"acteur:{str(platform).strip().lower()}",
            label=str(platform).strip(),
            body={"nom": str(platform).strip(), "role": "plateforme"}, event=event,
        )
        upsert_link(conn, order_id, "concerne", platform_id, event)
        created.append(platform_id)
    return created


def _apply_document(conn, event, payload):
    document_id = upsert_object(
        conn, "Document", f"document:{payload.get('file_hash') or event['event_id']}",
        label=event["envelope"]["label"], body=payload, event=event,
    )
    return [document_id]


_HANDLERS = {
    "PERCEPTION.InvoiceReceived": lambda conn, e: _apply_invoice(conn, e, _fields_of(e["payload"])),
    "PERCEPTION.StatementLine": lambda conn, e: _apply_statement_line(conn, e, _fields_of(e["payload"])),
    "PERCEPTION.OrderObserved": lambda conn, e: _apply_order(conn, e, _fields_of(e["payload"])),
    "PERCEPTION.FactObserved": lambda conn, e: _apply_document(conn, e, e["payload"]),
    "PERCEPTION.EmailReceived": lambda conn, e: _apply_document(conn, e, e["payload"]),
    "PERCEPTION.DocumentReceived": lambda conn, e: _apply_document(conn, e, e["payload"]),
}

_MANUAL_FORM_HANDLERS = {
    "facture": _apply_invoice,
    "depense": _apply_statement_line,
    "vente": _apply_order,
}


def apply(conn, event):
    """Replie un evenement (dict tel que renvoye par
    ``event_store.read``) en Objets/Liens. Les types d'evenements hors du
    perimetre du projecteur (regles, agents...) sont ignores sans erreur -
    chaque projection declare ses types sources (Conception 3.5).

    Returns:
        list[str]: identifiants des Objets crees/touches (vide si type ignore).
    """
    handler = _HANDLERS.get(event["type"])
    if handler is not None:
        return handler(conn, event)

    if event["type"] == "HUMAN.ManualEntry":
        payload = event["payload"]
        form_handler = _MANUAL_FORM_HANDLERS.get(payload.get("form"))
        if form_handler is not None:
            return form_handler(conn, event, _fields_of(payload))
        return _apply_document(conn, event, payload)

    return []


def apply_events(conn, events):
    """Replie une sequence d'evenements, dans l'ordre."""
    touched = []
    for event in events:
        touched.extend(apply(conn, event))
    return touched


def rebuild(conn, events):
    """Reconstruit le graphe **depuis zero** : vide la projection puis
    rejoue les evenements. Doit produire un etat strictement identique au
    repli incremental (invariant T-M09-1) - garanti par les identifiants
    deterministes et l'ordre stable du journal."""
    conn.execute("DELETE FROM links")
    conn.execute("DELETE FROM objects")
    conn.commit()
    return apply_events(conn, events)


def get_object(conn, object_id):
    row = conn.execute(
        "SELECT object_id, type, label, envelope_json, body_json, state, version "
        "FROM objects WHERE object_id = ?", (object_id,)
    ).fetchone()
    if row is None:
        return None
    return {"object_id": row[0], "type": row[1], "label": row[2],
            "envelope": json.loads(row[3]), "body": json.loads(row[4]),
            "state": row[5], "version": row[6]}


def neighbors(conn, object_id, direction="both"):
    """Traversee bidirectionnelle des Liens (T-M09-2).

    Args:
        direction: ``"out"`` (liens sortants), ``"in"`` (entrants) ou
            ``"both"``.

    Returns:
        list[dict]: ``{"link_id", "rel", "direction", "object"}`` - de
        toute facture on atteint le fournisseur, et inversement.
    """
    results = []
    if direction in ("out", "both"):
        for link_id, rel, dst in conn.execute(
            "SELECT link_id, rel, dst FROM links WHERE src = ?", (object_id,)
        ).fetchall():
            results.append({"link_id": link_id, "rel": rel, "direction": "out",
                            "object": get_object(conn, dst)})
    if direction in ("in", "both"):
        for link_id, rel, src in conn.execute(
            "SELECT link_id, rel, src FROM links WHERE dst = ?", (object_id,)
        ).fetchall():
            results.append({"link_id": link_id, "rel": rel, "direction": "in",
                            "object": get_object(conn, src)})
    return results


def snapshot_state(conn):
    """Photographie triee et canonique du graphe (objects + links), pour
    comparer deux etats (test de l'invariant de reconstruction)."""
    objects = conn.execute(
        "SELECT object_id, type, label, body_json, state, version, row_hash "
        "FROM objects ORDER BY object_id"
    ).fetchall()
    links = conn.execute(
        "SELECT link_id, src, rel, dst, weight FROM links ORDER BY link_id"
    ).fetchall()
    return {"objects": objects, "links": links}
