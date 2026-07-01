# Connecteurs API desactives

Ce dossier accueille, module par module, les connecteurs API futurs (banque,
Uber, Deliveroo, Meta, comptable...). **Aucun n'est implemente au MVP.**

Contrat figé (T-CONN-1, Sprint 8) :
- Chaque module `<x>_api.py` expose le meme contrat d'ingestion que la
  passerelle de perception (M04), mais **leve une erreur explicite**
  (`ConnecteurNonActive`) au lieu de produire la moindre donnee.
- Aucune donnee n'est jamais simulee ou inventee : en attendant l'activation,
  la source correspondante s'utilise via `data/inbox/` (fichier depose /
  email) - c'est le mode officiel, jamais un pis-aller.
- Activation future = brancher le module sur la passerelle M04, sans toucher
  au reste du systeme.

Ce dossier est vide au sens fonctionnel tant que T-CONN-1 (Sprint 8) n'est
pas construit.
