# Connecteurs API desactives (T-CONN-1)

Chaque source API future (banque, Uber Eats, Deliveroo, Meta, comptable)
a ici son module **inerte** : il expose le contrat d'ingestion
(`is_enabled()`, `fetch(conn)`, `EVENT_TYPE`) mais **leve
`ConnectorDisabledError` (« connecteur non activé ») avant toute
action** - il ne lit rien, n'ecrit rien, ne simule aucune API, ne
produit jamais la moindre donnee (Backlog, contraintes n.5-6 ; regle
anti-invention).

En attendant l'activation, chaque source s'utilise par **depot de
fichier** dans `data/inbox/` - c'est le mode officiel, pas un
pis-aller :

| Module | Source | En attendant, deposer |
|---|---|---|
| `bank_api.py` | banque (bank-feed) | export CSV du releve (profil `banque-releve`) |
| `uber_eats_api.py` | Uber Eats | export CSV des commandes (profil `plateforme-commandes`) |
| `deliveroo_api.py` | Deliveroo | export CSV des commandes (profil `plateforme-commandes`) |
| `meta_api.py` | Meta | export CSV des statistiques |
| `accounting_api.py` | logiciel comptable | balance XLSX (profil `balance-comptable`) |

**Activation future** = implementer `fetch` dans le module concerne pour
qu'il produise ses enregistrements bruts et les emballe via la meme
passerelle M04 (`perception.intake_folder.normalize_records`), sans
toucher au reste du systeme. Le message d'erreur de chaque connecteur
indique deja le fichier a deposer a la place.
