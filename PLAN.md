# Architecture — SmartThings Find (fork OAuth)

## Historique

- **v0.1–0.3** : fork modernisé de `Vedeneb/HA-SmartThings-Find`. Authentification
  par **login QR** Samsung Account, données via `smartthingsfind.samsung.com/*.do`
  + cookie `JSESSIONID` + jeton `_csrf`.
- **Rupture (2024–2025)** : Samsung a reconstruit `account.samsung.com` en SPA
  OAuth2/IAM avec anti-bot **DataDome**. Le login QR (`/accounts/v1/FMM2/
  signInWithQrCode`) renvoie 404. Le collage manuel du cookie `JSESSIONID`
  fonctionne mais **expire** (~semaines) sans renouvellement.
- **v0.4.0 (ce fork)** : bascule vers **OAuth 2.0 + PKCE**, en vendorisant
  l'implémentation éprouvée de
  [`PixelShober/HA-SmartThings-Find`](https://github.com/PixelShober/HA-SmartThings-Find)
  (MIT). Session **persistante et auto-renouvelée**.

## Authentification (OAuth 2.0 PKCE)

Fichier : `custom_components/smartthings_find/utils.py`.

1. `do_login_stage_one` : `GET account.samsung.com/accounts/ANDROIDSDK/getEntryPoint`
   → `signInURI`, clé publique PKI, `chkDoNum`. Génère PKCE (S256) et un
   `svcParam` chiffré (AES-128-CBC, clé enveloppée RSA/PKCS1v15). Construit l'URL
   de login (`clientId=yfrtglt53o`, `redirect_uri=ms-app://…`).
2. L'utilisateur se connecte **dans un vrai navigateur** (ce qui « passe »
   DataDome) et colle l'URL de redirection `ms-app://…` (capturée via DevTools).
3. `do_login_stage_two` : déchiffre les paramètres du redirect, puis
   `POST {auth_server}/auth/oauth2/authenticate` (grant `authorization_code`) →
   `userauth_token`. Enchaîne deux `authorize`+`token` :
   - service Find : `client_id=27zmg0v1oo`, scope `offline.access` ;
   - SmartThings IoT : `client_id=6iado3s6jc`, scope `iot.client`.
   → `access_token` + `refresh_token` (Find et IoT).
4. `_refresh_token` / `refresh_find_token` / `refresh_iot_token` : renouvellent
   les jetons via grant `refresh_token`. Les nouveaux jetons sont réécrits dans
   l'entrée de configuration.

Constantes (client_ids, scopes) : `const.py`.

## Couche données (API cloud SmartThings)

Contrairement aux versions précédentes, les données ne passent **plus** par
`*.do`. Elles transitent par l'API cloud SmartThings, jeton IoT en `Bearer` :

- `GET auth.api.smartthings.com/users/me` → UUID utilisateur.
- `GET api.smartthings.com/installedapps?allowed=true` → `installedAppId` du
  plugin `com.samsung.android.plugin.fme`.
- `POST api.smartthings.com/installedapps/{id}/execute` → liste d'appareils
  (`get_devices`), localisation (`get_device_location`), sonnerie (`ring_device`,
  `stop_ring_device`).

En-têtes : `_get_find_headers` (jetons Find `X-Sec-Sa-*`) et
`_get_smartthings_headers` (Bearer IoT). Rafraîchissement automatique des jetons
sur 401/403.

## Entités (plateformes)

`__init__.py` porte le `DataUpdateCoordinator`. Plateformes :
`device_tracker`, `sensor` (batterie), `switch` (sonnerie).

## Dépendances

`manifest.json` → `cryptography` (chiffrement du `svcParam`), `pytz` (fuseaux).

## Attribution

Code OAuth vendorisé depuis `PixelShober/HA-SmartThings-Find` (MIT), lui-même
dérivé de `tomskra` puis `Vedeneb`. Voir `LICENSE`.
