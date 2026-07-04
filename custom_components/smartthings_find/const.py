"""Constantes de l'intégration SmartThings Find."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "smartthings_find"

# Plateformes exposées par l'intégration
PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
    Platform.SENSOR,
]

# --- Clés de configuration / options ---
CONF_JSESSIONID = "jsessionid"

CONF_ACTIVE_MODE_SMARTTAGS = "active_mode_smarttags"
CONF_ACTIVE_MODE_OTHERS = "active_mode_others"
CONF_ACTIVE_MODE_SMARTTAGS_DEFAULT = True
CONF_ACTIVE_MODE_OTHERS_DEFAULT = False

CONF_UPDATE_INTERVAL = "update_interval"
CONF_UPDATE_INTERVAL_DEFAULT = 120
CONF_UPDATE_INTERVAL_MIN = 30

# Correspondance des niveaux de batterie symboliques renvoyés par l'API
BATTERY_LEVELS: dict[str, int] = {
    "FULL": 100,
    "MEDIUM": 50,
    "LOW": 15,
    "VERY_LOW": 5,
}

# Métadonnées appareil
MANUFACTURER = "Samsung"
CONFIGURATION_URL = "https://smartthingsfind.samsung.com/"

# Types d'appareils / sous-types
DEVICE_TYPE_TAG = "TAG"
SUBTYPE_EARBUDS = "CANAL2"  # écouteurs à sous-localisation gauche/droite

# --- Endpoints Samsung (reverse-engineering, repris fidèlement du dépôt source
#     Vedeneb/HA-SmartThings-Find). NE PAS inventer / modifier sans preuve. ---

# Portail de connexion Samsung Account (login par QR code)
URL_PRE_SIGNIN = (
    "https://account.samsung.com/accounts/v1/FMM2/signInGate"
    "?state={state}"
    "&redirect_uri=https:%2F%2Fsmartthingsfind.samsung.com%2Flogin.do"
    "&response_type=code&client_id=ntly6zvfpn&scope=iot.client"
    "&locale=de_DE&acr_values=urn:samsungaccount:acr:basic"
    "&goBackURL=https:%2F%2Fsmartthingsfind.samsung.com%2Flogin"
)
URL_QR_CODE_SIGNIN = "https://account.samsung.com/accounts/v1/FMM2/signInWithQrCode"
URL_SIGNIN_XHR = "https://account.samsung.com/accounts/v1/FMM2/signInXhr"
URL_QR_POLL = "https://account.samsung.com/accounts/v1/FMM2/signInWithQrCodeProc"
URL_SIGNIN_SUCCESS = "https://account.samsung.com{next_url}"

# API SmartThings Find (nécessite le cookie JSESSIONID + le jeton _csrf)
URL_GET_CSRF = "https://smartthingsfind.samsung.com/chkLogin.do"
URL_DEVICE_LIST = "https://smartthingsfind.samsung.com/device/getDeviceList.do"
URL_ADD_OPERATION = "https://smartthingsfind.samsung.com/dm/addOperation.do"
URL_SET_LAST_DEVICE = "https://smartthingsfind.samsung.com/device/setLastSelect.do"

# Durée max d'attente du scan du QR code (secondes)
QR_POLL_TIMEOUT = 120
QR_POLL_INTERVAL = 2
