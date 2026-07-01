"""Deduplication (empreinte fichier + empreinte ligne) - T-M08-1.

Garantit l'idempotence de l'ingestion (Constitution, principes Data :
"cles stables ; deduplication par empreinte ; idempotence garantie").
Deux mecanismes complementaires (Conception, section 8.5) :

- **Empreinte fichier** : ``file_hash`` + ``file_seen`` s'appuient sur
  ``ingestion_log`` (une ligne par tentative d'ingestion, indexee par le
  hash du contenu) - rejouer le meme fichier n'est jamais retraite comme
  neuf.
- **Empreinte ligne** : ``row_hash`` calcule une empreinte stable sur les
  colonnes-cles d'un enregistrement, base de la deduplication ligne-a-
  ligne des futurs parseurs CSV/XLSX (Sprint 3).
"""
import hashlib
import json

_CHUNK_SIZE = 65536


def file_hash(path):
    """Empreinte SHA-256 du contenu d'un fichier (independante du nom)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_seen(conn, hash_):
    """True si ce contenu de fichier a deja fait l'objet d'une tentative
    d'ingestion (``ingestion_log``), quel qu'en soit le nom de fichier."""
    row = conn.execute(
        "SELECT 1 FROM ingestion_log WHERE file_hash = ? LIMIT 1", (hash_,)
    ).fetchone()
    return row is not None


def record_ingestion(
    conn,
    import_id,
    source,
    file,
    hash_,
    records,
    new_records,
    duplicates,
    anomalies,
    errors,
    status,
    ts,
    note=None,
):
    """Journalise une tentative d'ingestion de fichier dans
    ``ingestion_log`` - la trace qui rend ``file_seen`` possible."""
    conn.execute(
        """
        INSERT INTO ingestion_log (
            import_id, ts, source, file, file_hash, records, new_records,
            duplicates, anomalies, errors, status, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (import_id, ts, source, file, hash_, records, new_records,
         duplicates, anomalies, errors, status, note),
    )
    conn.commit()
    return import_id


def row_hash(record, keycols):
    """Empreinte stable sur les colonnes-cles ``keycols`` d'un
    enregistrement - deux enregistrements avec les memes valeurs sur ces
    colonnes ont la meme empreinte, quelles que soient leurs autres
    differences (utilise par les futurs parseurs CSV/XLSX pour la
    deduplication ligne-a-ligne)."""
    key_values = {col: record.get(col) for col in keycols}
    canonical = json.dumps(key_values, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
