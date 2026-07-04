# PLAN — Modernisation de HA-SmartThings-Find

Dépôt source (archivé mais fonctionnel) :
**https://github.com/Vedeneb/HA-SmartThings-Find** (auteur : Benedikt Frey, MIT).
Reverse-engineering de l'API SmartThings Find de Samsung (login QR + JSESSIONID).

Ce document liste ce qui a été **repris**, ce qui a été **modernisé**, ce qui
**reste à tester** avec le compte Samsung de Julie, et les étapes pour **publier**.

---

## 1. Fichiers du dépôt source étudiés

Tous récupérés et lus (via `raw.githubusercontent.com`) :

| Fichier source | Statut |
| --- | --- |
| `README.md` | lu |
| `hacs.json` | lu |
| `LICENSE` (MIT, © 2024 Benedikt Frey) | lu |
| `.gitignore` | lu |
| `.github/workflows/validate.yaml` | lu |
| `custom_components/smartthings_find/manifest.json` | lu |
| `.../__init__.py` | lu |
| `.../config_flow.py` | lu |
| `.../const.py` | lu |
| `.../utils.py` (587 lignes — cœur API/auth) | lu |
| `.../device_tracker.py` | lu |
| `.../sensor.py` | lu |
| `.../button.py` | lu |
| `.../translations/en.json`, `de.json` | lu |
| `media/screenshot_1.png` | **non récupéré** (binaire, non nécessaire) |

Aucun fichier source attendu n'était introuvable.

---

## 2. Logique reprise fidèlement (reverse-engineering — NON réinventé)

### Authentification (login QR en 2 étapes)
Reprise à l'identique dans `api.py` (`do_login_stage_one`, `do_login_stage_two`,
`fetch_csrf`, `gen_qr_code_base64`) :

1. `signInGate` (pose des cookies) avec un `state` aléatoire + `client_id=ntly6zvfpn`.
2. `signInWithQrCode` → extraction de l'URL `https://signin.samsung.com/key/…`.
3. `signInXhr` → jeton `_csrf`.
4. Sondage `signInWithQrCodeProc` (header `X-Csrf-Token`) jusqu'à `rtnCd=SUCCESS`.
5. Suivi de `nextURL` → premier `JSESSIONID` (non valable STF).
6. Extraction du `window.location.href` (redirect `login.do?...&code=...`) → suivi
   → **`JSESSIONID` valable pour SmartThings Find**, stocké dans l'entrée de config.
7. `chkLogin.do` → header `_csrf` réutilisé pour chaque requête suivante.

### Endpoints Samsung (repris verbatim, centralisés dans `const.py`)
- `account.samsung.com/accounts/v1/FMM2/signInGate|signInWithQrCode|signInXhr|signInWithQrCodeProc`
- `smartthingsfind.samsung.com/chkLogin.do` (récupération du `_csrf`)
- `smartthingsfind.samsung.com/device/getDeviceList.do`
- `smartthingsfind.samsung.com/device/setLastSelect.do` (récupération localisation)
- `smartthingsfind.samsung.com/dm/addOperation.do` (mise à jour active + **sonnerie RING**)

### Payloads & parsing (repris à l'identique)
- `setLastSelect` : `{"dvceId":…, "removeDevice":[]}`.
- Mise à jour active : `{"dvceId":…, "operation":"CHECK_CONNECTION_WITH_LOCATION", "usrId":…}`.
- Sonnerie : `{"dvceId":…, "operation":"RING", "usrId":…, "status":"start", "lockMessage":…}`.
- Sélection de la meilleure localisation parmi `LOCATION` / `LASTLOC` / `OFFLINE_LOC`,
  gestion des `encLocation` (chiffrées ignorées), date `gpsUtcDt` au format `%Y%m%d%H%M%S`.
- Précision GPS = √(horizontalUncertainty² + verticalUncertainty²).
- Batterie : table `FULL/MEDIUM/LOW/VERY_LOW` + repli entier, opération `CHECK_CONNECTION`.
- Sous-localisation écouteurs (`CANAL2`, gauche/droite) via `encLocation`.
- Double `html.unescape` sur `modelName`, filtrage des appareils désactivés dans le registre.

---

## 3. Ce qui a été modernisé

### Architecture
- **`utils.py` → `api.py`** : le client API ne lit plus dans `hass.data`. Les
  fonctions reçoivent des **paramètres explicites** (`session`, `csrf_token`,
  drapeau `active`). Endpoints et payloads inchangés.
- **Nouveau `coordinator.py`** : `SmartThingsFindCoordinator` porte lui-même
  l'état (session, `JSESSIONID`, `_csrf`, liste d'appareils, modes actifs) au lieu
  du dictionnaire `hass.data[DOMAIN][entry_id]`. Méthode `async_setup()` (auth +
  chargement appareils) + `async_refresh_csrf()`.
- **`entry.runtime_data`** (HA ≥ 2024.6) remplace `hass.data` pour transporter le
  coordinateur vers les plateformes. Alias typé `STFConfigEntry`.
- **`__init__.py`** : `async_forward_entry_setups` désormais **attendu** (le source
  faisait un `async_create_task` détaché) ; `async_unload_entry` simplifié ;
  `add_update_listener` pour recharger sur changement d'options.

### Entités (API HA récentes)
- `device_tracker` et `sensor` héritent désormais de **`CoordinatorEntity`**
  (au lieu du câblage manuel `coordinator.async_add_listener`).
- Adoption de **`_attr_has_entity_name = True`** + clés de traduction
  (`battery`, `ring`) → nommage moderne « <Appareil> Batterie / Faire sonner ».
- `sensor` : `native_value` + `_attr_native_unit_of_measurement = PERCENTAGE`
  (remplace les propriétés dépréciées `state` / `unit_of_measurement`).
- `device_tracker` : `SourceType`/`TrackerEntity` importés depuis le package
  `homeassistant.components.device_tracker`, accès défensifs (`.get`, `or {}`).

### config_flow
- **`OptionsFlowWithConfigEntry` (déprécié, retiré en 2025.12) → `OptionsFlow`**
  standard ; `self.config_entry` implicite ; lecture via `self.config_entry.options`.
- `async_get_options_flow` retourne l'`OptionsFlow` **sans argument** (plus de
  `config_entry` passé au constructeur, déprécié).
- `async_show_progress` appelé avec **`step_id`** (désormais requis).
- Reauth : signature `async_step_reauth(entry_data)`, étape `reauth_confirm` dédiée,
  réinitialisation des tâches avant relance du login.
- Attributs de classe déplacés dans `__init__` (fin des attributs de classe mutables
  partagés entre instances de flux).

### Divers
- **`pytz` supprimé** → `datetime.timezone.utc`.
- `button.py` : f-string multi-ligne bancale du source supprimée ; URL centralisée ;
  la sonnerie passe par `api.async_ring_device`.
- **`manifest.json`** : version `0.2.1 → 0.3.0` ; `requirements` corrigé
  `["requests","qrcode"]` → **`["qrcode[pil]==7.4.2"]`** (`requests` inutilisé,
  `qrcode` a besoin de Pillow) ; ajout `loggers` ; `codeowners`/URLs → `juliewaymel`.
- **Traductions** : `strings.json` (base) + `translations/en|fr|de.json`, ajout du
  **français** et des clés d'entités.
- `hacs.json` : ajout `homeassistant: "2024.12.0"`.
- Commentaires/messages en **français** ; `README.md` FR avec avertissement
  « non officiel / reverse-engineering / peut casser ».

---

## 4. À TESTER avec le compte Samsung de Julie

> Rien n'a pu être exécuté ici : **aucun interpréteur Python/Node/jq** disponible
> sur la machine (le `python` présent est le stub WindowsApps). La validation
> `py_compile` / `hassfest` / `ConvertFrom-Json` reste donc à faire côté HA / CI.

1. **Compilation & chargement** : copier dans `config/custom_components/`, redémarrer
   HA, vérifier l'absence d'erreur d'import (surtout `type STFConfigEntry` → **exige
   Python 3.12+**, OK sur HA 2024.12+).
2. **Login QR** : le QR s'affiche-t-il ? Scan depuis le **Z Fold4** → session OK ?
   (endpoints Samsung inchangés, mais le portail `account.samsung.com` peut avoir
   évolué depuis l'archivage du source → **point de rupture le plus probable**).
3. **Liste d'appareils** : Z Fold4, montre, écouteurs (Buds → tracker G/D ?),
   **SmartTags** bien détectés ? `modelName` correct (dé-échappement) ?
4. **Localisation** : positions et précision cohérentes ? Comportement
   **mode passif vs actif** (option) ? Gestion des localisations chiffrées.
5. **Batterie** : capteur `%` correct par appareil (absent pour écouteurs).
6. **Sonnerie (bouton RING)** : fait bien sonner le téléphone / le tag ?
   Vérifier le contournement **DND / Ne pas déranger** (le `lockMessage` et
   l'opération RING doivent sonner même en silencieux — à confirmer en conditions
   réelles ; c'est un comportement côté Samsung, non garanti).
7. **Expiration de session** : au bout de X heures/jours, le flux de **reauth**
   se déclenche-t-il proprement (404 / `Logout` / 401 → `ConfigEntryAuthFailed`) ?
8. **Options** : changer l'intervalle / les modes actifs → rechargement auto.
9. **Appareil désactivé** : désactiver un appareil dans le registre → bien ignoré.

---

## 5. Publication (proposer le dépôt)

### a. Créer le dépôt GitHub `juliewaymel/ha-smartthings-find`
```bash
cd C:\Users\julie\ha-smartthings-find
git init
git add .
git commit -m "Fork modernisé de Vedeneb/HA-SmartThings-Find (v0.3.0)"
gh repo create juliewaymel/ha-smartthings-find --public --source=. --push
```
- Renseigner description + topics : `home-assistant`, `hacs`, `smartthings`,
  `samsung`, `smarttag`, `device-tracker`.
- **Créditer** l'auteur original (déjà fait dans README + LICENSE).
- Ajouter une **release git taggée `v0.3.0`** (`gh release create v0.3.0`) — requis
  par HACS.

### b. Validation CI (avant soumission HACS)
- Le workflow `.github/workflows/validate.yaml` lance **hassfest** + **action HACS**.
  Vérifier qu'ils passent au vert.
- Idéalement, tester en local avec `python -m script.hassfest` sur une checkout HA,
  ou simplement via l'action GitHub.

### c. Ajout comme dépôt personnalisé HACS (usage immédiat)
HACS → Dépôts personnalisés → URL du repo, catégorie **Intégration**. Utilisable
sans attendre la validation dans le catalogue par défaut.

### d. Soumission au catalogue HACS par défaut (optionnel, plus long)
- Respecter les exigences HACS (repo public, release, `hacs.json`, `README`, hassfest OK,
  brand ajoutée si besoin dans `home-assistant/brands`).
- Ouvrir une PR sur [`hacs/default`](https://github.com/hacs/default) ajoutant le repo.

### e. Ajout de la marque (logo) — recommandé
- PR sur [`home-assistant/brands`](https://github.com/home-assistant/brands) pour le
  domaine `smartthings_find` (icône), afin d'avoir un joli logo dans l'UI HA.

### f. Post forum Home Assistant Community
- Publier dans **Share your Projects / Custom Components** : présenter le fork,
  l'origine (Vedeneb archivé), les fonctionnalités, l'avertissement « non officiel »,
  le lien HACS, appel à testeurs (SmartTags, Buds, montres).
- Éventuellement signaler le fork en **issue** sur le dépôt source archivé pour
  rediriger les utilisateurs.

---

## 6. Points de vigilance / dette restante

- **Rupture API Samsung** = risque n°1 (portail login surtout). Prévoir des logs clairs.
- Localisations **chiffrées** non déchiffrées (comme le source) — endpoint
  `getEncToken` non exploité.
- Pas encore de **tests unitaires** (dossier `tests/` à ajouter pour la CI HA).
- `requirements` **`qrcode[pil]==7.4.2`** : à ajuster si conflit avec la version de
  Pillow embarquée par HA.
- `quality_scale` non déclaré (le fork reste une intégration custom, hors core).
