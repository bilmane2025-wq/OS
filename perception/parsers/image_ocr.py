"""OCR image + confirmation manuelle - le mode manuel reste l'officiel
(T-M06-2).

Cycle impose par le backlog : **OCR -> proposition -> confirmation
humaine**. ``read`` lit un ticket/une photo via un moteur OCR **local**
(pytesseract si installe ; injectable pour les tests) et produit des
champs **proposes**, tous etiquetes ``nature="estimé"`` avec une
confiance basse - jamais des faits. **Rien n'entre en « mesuré » sans
confirmation humaine** : seule ``confirm`` - un acteur humain autorise
(M28), trace (M29) - transforme les valeurs confirmees en evenement
``PERCEPTION.InvoiceReceived`` de nature ``mesuré``, accompagne d'un
``HUMAN.Validation``.

Si aucun moteur OCR local n'est disponible, ``read`` ne propose rien et
le demande explicitement (anomalie « saisie manuelle requise ») - jamais
de valeur inventee, et le mode manuel officiel prend le relais.
"""
import json
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store
from core.envelope import make_envelope
from governance import identity_access, permissions

PROPOSED_NATURE = "estimé"
PROPOSED_SCORE = 0.3  # confiance basse : une lecture machine non confirmee

_AMOUNT_RE = re.compile(r"(?:total|montant)\s*[:=]?\s*([0-9]+[.,][0-9]{2})", re.IGNORECASE)
_DATE_RE = re.compile(r"([0-9]{2}[/-][0-9]{2}[/-][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})")


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_engine(path):
    """Moteur OCR local par defaut : pytesseract s'il est installe (aucun
    telechargement, aucun appel externe). ``None`` sinon - jamais un faux
    texte."""
    try:
        import pytesseract  # noqa: F401 - dependance optionnelle locale
        from PIL import Image
    except ImportError:
        return None
    try:
        return pytesseract.image_to_string(Image.open(path))
    except Exception:
        return None


def read(path, engine=None):
    """Lit une image et **propose** des champs estimes.

    Args:
        path: chemin de l'image (ticket, photo de facture).
        engine: callable ``path -> texte | None`` (defaut :
            ``default_engine``). L'injection permet de tester le cycle
            sans dependre d'un binaire OCR installe.

    Returns:
        dict: ``{"proposals": {champ: {"value", "nature", "score"}},
        "ocr_available": bool, "raw_text": str|None}``. Chaque
        proposition est ``nature="estimé"``, score bas - l'humain
        confirme avant tout passage en mesure.
    """
    engine = engine or default_engine
    text = engine(path)
    if text is None:
        return {"proposals": {}, "ocr_available": False, "raw_text": None}

    proposals = {}
    amount_match = _AMOUNT_RE.search(text)
    if amount_match:
        proposals["montant"] = {"value": amount_match.group(1),
                                "nature": PROPOSED_NATURE, "score": PROPOSED_SCORE}
    date_match = _DATE_RE.search(text)
    if date_match:
        proposals["date"] = {"value": date_match.group(1),
                             "nature": PROPOSED_NATURE, "score": PROPOSED_SCORE}

    return {"proposals": proposals, "ocr_available": True, "raw_text": text}


def request_manual_entry(conn, path):
    """Aucun moteur OCR ou aucune proposition exploitable : demande de
    saisie manuelle tracee (anomalie) - jamais une valeur inventee."""
    now = _now_iso()
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                               recommendation, state, created_at, refs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly_id, "perception/saisie-manuelle-requise", "moyenne", 1.0, None,
         "Lecture OCR indisponible ou incomplete : saisir le document via le "
         "formulaire manuel (mode officiel).",
         "ouverte", now,
         json.dumps({"file": os.path.basename(path)}, ensure_ascii=False)),
    )
    conn.commit()
    return anomaly_id


def confirm(conn, path, proposals, confirmed_fields, author):
    """Confirmation humaine : les valeurs **confirmees par l'humain**
    (eventuellement corrigees) deviennent un fait mesure.

    - Controle M28 : l'auteur doit disposer de l'autorite « OcrConfirm »
      (N1) - jamais une confirmation anonyme ou automatique.
    - Trace M29 : la confirmation est journalisee (qui/quoi/quand).
    - Ecrit ``HUMAN.Validation`` (la decision humaine) puis
      ``PERCEPTION.InvoiceReceived`` de nature ``mesuré`` (le fait issu du
      document, desormais confirme).

    Args:
        proposals: la sortie de ``read`` (ce que la machine proposait).
        confirmed_fields: dict ``{champ: valeur}`` valide par l'humain.
        author: acteur humain (``"human:..."``).

    Returns:
        dict: ``{"validation_event_id", "measured_event_id"}``.
    """
    permissions.check(conn, author, {"object_type": "OcrConfirm",
                                     "action": "ocr-confirm",
                                     "required_authority": 1})

    now = _now_iso()
    validation_envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="HUMAN.Validation",
        label=f"Confirmation OCR : {os.path.basename(path)}",
        source=f"inbox/{os.path.basename(path)}",
        author=author,
        valid_from=now, ts_record=now,
        nature="fait", score=1.0,
        owner=author, visibility="interne", authority=1,
    )
    _, validation_event_id = event_store.append(
        conn, validation_envelope,
        payload={"proposals": proposals.get("proposals", proposals),
                 "confirmed": dict(confirmed_fields)},
    )

    measured_envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="PERCEPTION.InvoiceReceived",
        label=f"Document confirme : {os.path.basename(path)}",
        source=f"inbox/{os.path.basename(path)}",
        author=author,
        valid_from=now, ts_record=now,
        nature="mesuré",  # mesure *parce que* confirme par l'humain
        score=0.95,
        owner=author, visibility="interne", authority=1,
        event_id=validation_event_id,  # cause : la validation humaine
    )
    _, measured_event_id = event_store.append(
        conn, measured_envelope,
        payload={"fields": dict(confirmed_fields), "file": os.path.basename(path)},
        causation_id=validation_event_id,
    )

    identity_access.log_access(conn, author, "ocr-confirm", measured_event_id)
    return {"validation_event_id": validation_event_id,
            "measured_event_id": measured_event_id}
