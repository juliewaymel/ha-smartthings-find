"""Client bas niveau pour l'API (non officielle) SmartThings Find.

Toute la mécanique d'authentification (login QR Samsung Account), la liste des
appareils et la récupération de localisation sont reprises fidèlement du dépôt
source `Vedeneb/HA-SmartThings-Find`. Les endpoints ne sont PAS inventés : ils
proviennent du reverse-engineering d'origine (voir const.py).

La seule modernisation ici est structurelle : les fonctions reçoivent des
paramètres explicites (session, jeton _csrf, drapeau « active ») au lieu de
lire dans `hass.data`. La logique réseau et les charges utiles sont conservées.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import random
import re
import string
from datetime import datetime, timedelta, timezone
from io import BytesIO

import aiohttp
import qrcode

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    BATTERY_LEVELS,
    CONFIGURATION_URL,
    DOMAIN,
    MANUFACTURER,
    QR_POLL_INTERVAL,
    QR_POLL_TIMEOUT,
    URL_ADD_OPERATION,
    URL_DEVICE_LIST,
    URL_GET_CSRF,
    URL_PRE_SIGNIN,
    URL_QR_CODE_SIGNIN,
    URL_QR_POLL,
    URL_SET_LAST_DEVICE,
    URL_SIGNIN_SUCCESS,
    URL_SIGNIN_XHR,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentification (login QR en deux étapes)
# ---------------------------------------------------------------------------
async def do_login_stage_one(hass: HomeAssistant) -> tuple[aiohttp.ClientSession, str] | None:
    """Étape 1 du login : prépare la session et extrait l'URL du QR code.

    Génère un paramètre `state` aléatoire, ouvre la page de connexion (qui pose
    des cookies), puis la page « login par QR code » et en extrait l'URL
    encodée dans le QR (https://signin.samsung.com/key/xxxx).

    Retourne (session, qr_url) en cas de succès, sinon None.
    """
    session = async_get_clientsession(hass)
    session.cookie_jar.clear()

    # Paramètre `state` aléatoire (client_id semble statique pour STF)
    state = "".join(random.choices(string.ascii_letters + string.digits, k=16))

    try:
        # Page de connexion initiale (pose des cookies)
        async with session.get(URL_PRE_SIGNIN.format(state=state)) as res:
            if res.status != 200:
                _LOGGER.error("Pré-login échoué, statut %s", res.status)
                return None
            _LOGGER.debug("Étape 1 (pré-login) : statut %s", res.status)

        # Page « login par QR code »
        async with session.get(URL_QR_CODE_SIGNIN) as res:
            if res.status != 200:
                _LOGGER.error("Requête QR code échouée, statut %s", res.status)
                return None
            text = await res.text()
            _LOGGER.debug("Étape 2 (URL QR code) : statut %s", res.status)

        # L'URL encodée dans le QR ressemble à : https://signin.samsung.com/key/abcd
        match = re.search(r"https://signin\.samsung\.com/key/[^'\"]+", text)
        if not match:
            _LOGGER.error("URL du QR code introuvable dans la réponse")
            return None

        qr_url = match.group(0)
        _LOGGER.info("URL du QR code extraite : %s", qr_url)
        return session, qr_url

    except Exception as err:  # noqa: BLE001 - on journalise tout échec réseau
        _LOGGER.error("Erreur pendant le login (étape 1) : %s", err, exc_info=True)
        return None


async def do_login_stage_two(session: aiohttp.ClientSession) -> str | None:
    """Étape 2 du login : attend le scan du QR puis récupère le JSESSIONID.

    Récupère le jeton _csrf, sonde le serveur jusqu'à ce que l'utilisateur
    scanne et valide le QR, suit les redirections et retourne le cookie
    JSESSIONID valable pour SmartThings Find. Retourne None en cas d'échec.
    """
    try:
        # Récupère le _csrf à envoyer avec chaque requête de sondage
        async with session.get(URL_SIGNIN_XHR) as res:
            if res.status != 200:
                _LOGGER.error("Requête XHR de login échouée, statut %s", res.status)
                return None
            json_res = await res.json()
            _LOGGER.debug("Étape 3 (XHR login) : statut %s", res.status)

        csrf_token = json_res.get("_csrf", {}).get("token")
        if not csrf_token:
            _LOGGER.error("Jeton _csrf introuvable dans la réponse XHR")
            return None

        end_time = datetime.now() + timedelta(seconds=QR_POLL_TIMEOUT)
        next_url: str | None = None

        # Sondage : {"rtnCd":"POLLING"} tant que non scanné, puis
        # {"rtnCd":"SUCCESS","nextURL":"..."} une fois validé.
        while datetime.now() < end_time:
            try:
                await asyncio.sleep(QR_POLL_INTERVAL)
                async with session.post(
                    URL_QR_POLL, json={}, headers={"X-Csrf-Token": csrf_token}
                ) as res:
                    if res.status != 200:
                        _LOGGER.error("Sondage QR échoué, statut %s", res.status)
                        continue
                    js = await res.json()
                    _LOGGER.debug("Étape 4 (sondage QR) : statut %s", res.status)

                if js.get("rtnCd") == "SUCCESS":
                    next_url = js.get("nextURL")
                    break
            except aiohttp.ClientError as err:
                _LOGGER.error("Requête de sondage QR échouée : %s", err)
                return None

        if not next_url:
            _LOGGER.error("QR code non scanné dans le délai imparti")
            return None

        # Suit `next_url` (pose un premier JSESSIONID, pas encore valable pour STF)
        async with session.get(URL_SIGNIN_SUCCESS.format(next_url=next_url)) as res:
            if res.status != 200:
                _LOGGER.error("URL de succès login échouée, statut %s", res.status)
                return None
            text = await res.text()
            _LOGGER.debug("Étape 5 (succès login) : statut %s", res.status)

        # La réponse contient une redirection JS vers login.do?...&code=...
        match = re.search(r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", text)
        if not match:
            _LOGGER.error("URL de redirection introuvable après le login")
            return None

        redirect_url = match.group(1)
        _LOGGER.debug("URL de redirection trouvée : %s", redirect_url)

        # Suit la redirection : pose enfin le JSESSIONID valable pour STF
        async with session.get(redirect_url) as res:
            if res.status != 200:
                _LOGGER.error("Requête de redirection échouée, statut %s", res.status)
                return None
            _LOGGER.debug("Étape 6 (redirection) : statut %s", res.status)

        jsessionid = session.cookie_jar.filter_cookies(
            "https://smartthingsfind.samsung.com"
        ).get("JSESSIONID")
        if not jsessionid:
            _LOGGER.error("JSESSIONID absent des cookies")
            return None

        _LOGGER.debug("JSESSIONID récupéré : %s...", jsessionid.value[:20])
        return jsessionid.value

    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Erreur pendant le login (étape 2) : %s", err, exc_info=True)
        return None


async def fetch_csrf(session: aiohttp.ClientSession) -> str:
    """Récupère le jeton _csrf à joindre aux requêtes STF suivantes.

    Le cookie JSESSIONID doit déjà être présent dans la session.
    Lève ConfigEntryAuthFailed si l'authentification n'est plus valable.
    """
    async with session.get(URL_GET_CSRF) as response:
        if response.status == 200:
            csrf_token = response.headers.get("_csrf")
            if csrf_token:
                _LOGGER.debug("Nouveau jeton _csrf récupéré")
                return csrf_token
            err_msg = (
                "Jeton _csrf absent des en-têtes de réponse "
                f"(statut {response.status})"
            )
        else:
            err_msg = (
                f"Échec d'authentification STF [{response.status}] : "
                f"{await response.text()}"
            )

    _LOGGER.error(err_msg)
    raise ConfigEntryAuthFailed(err_msg)


# ---------------------------------------------------------------------------
# Liste des appareils
# ---------------------------------------------------------------------------
async def get_devices(
    hass: HomeAssistant, session: aiohttp.ClientSession, csrf_token: str
) -> list[dict]:
    """Récupère la liste des appareils du compte SmartThings Find.

    Retourne une liste de dicts {"data": <appareil>, "ha_dev_info": DeviceInfo}.
    Les appareils désactivés dans le registre HA sont ignorés.
    """
    url = f"{URL_DEVICE_LIST}?_csrf={csrf_token}"
    async with session.post(
        url, headers={"Accept": "application/json"}, data={}
    ) as response:
        if response.status != 200:
            _LOGGER.error(
                "Échec de récupération des appareils [%s] : %s",
                response.status,
                await response.text(),
            )
            if response.status == 404:
                # Session invalide -> déclenche la ré-authentification
                raise ConfigEntryAuthFailed("getDeviceList a renvoyé 404")
            return []

        response_json = await response.json()
        devices_data = response_json["deviceList"]
        registry = dr.async_get(hass)
        devices: list[dict] = []

        for device in devices_data:
            # Double dé-échappement HTML (ex : "Benedev&amp;#39;s S22" -> "Benedev's S22")
            device["modelName"] = html.unescape(html.unescape(device["modelName"]))

            identifier = (DOMAIN, device["dvceID"])
            ha_dev = registry.async_get_device({identifier})
            if ha_dev and ha_dev.disabled:
                _LOGGER.debug(
                    "Appareil désactivé ignoré : '%s' (par %s)",
                    device["modelName"],
                    ha_dev.disabled_by,
                )
                continue

            ha_dev_info = DeviceInfo(
                identifiers={identifier},
                manufacturer=MANUFACTURER,
                name=device["modelName"],
                model=device.get("modelID"),
                configuration_url=CONFIGURATION_URL,
            )
            devices.append({"data": device, "ha_dev_info": ha_dev_info})
            _LOGGER.debug("Appareil ajouté : %s", device["modelName"])

        return devices


# ---------------------------------------------------------------------------
# Localisation d'un appareil
# ---------------------------------------------------------------------------
async def get_device_location(
    session: aiohttp.ClientSession,
    csrf_token: str,
    dev_data: dict,
    active: bool,
) -> dict | None:
    """Demande (optionnellement) une mise à jour puis récupère la localisation.

    En mode « actif », envoie d'abord une opération CHECK_CONNECTION_WITH_LOCATION
    (consomme de la batterie côté appareil). Puis sélectionne la localisation la
    plus récente parmi les opérations LOCATION / LASTLOC / OFFLINE_LOC.
    Lève ConfigEntryAuthFailed si la session a expiré.
    """
    dev_id = dev_data["dvceID"]
    dev_name = dev_data["modelName"]

    set_last_payload = {"dvceId": dev_id, "removeDevice": []}
    update_payload = {
        "dvceId": dev_id,
        "operation": "CHECK_CONNECTION_WITH_LOCATION",
        "usrId": dev_data["usrId"],
    }

    try:
        if active:
            _LOGGER.debug("[%s] Mode actif : demande de mise à jour de localisation", dev_name)
            async with session.post(
                f"{URL_ADD_OPERATION}?_csrf={csrf_token}", json=update_payload
            ):
                pass
        else:
            _LOGGER.debug("[%s] Mode passif : pas de demande de mise à jour", dev_name)

        async with session.post(
            f"{URL_SET_LAST_DEVICE}?_csrf={csrf_token}",
            json=set_last_payload,
            headers={"Accept": "application/json"},
        ) as response:
            _LOGGER.debug("[%s] Réponse localisation (%s)", dev_name, response.status)

            if response.status != 200:
                res_text = await response.text()
                _LOGGER.error("[%s] Échec récupération localisation (%s)", dev_name, response.status)
                _LOGGER.debug("[%s] Réponse complète : '%s'", dev_name, res_text)
                # Session invalide : rafraîchir le _csrf ne suffit pas -> reauth
                if res_text == "Logout" or response.status == 401:
                    raise ConfigEntryAuthFailed(
                        f"Session STF invalide (statut {response.status})"
                    )
                return None

            data = await response.json()

        res: dict = {
            "dev_name": dev_name,
            "dev_id": dev_id,
            "update_success": True,
            "location_found": False,
            "used_op": None,
            "used_loc": None,
            "ops": [],
        }

        operations = data.get("operation") or []
        if not operations:
            _LOGGER.warning("[%s] Aucune opération dans la réponse ; échec de mise à jour", dev_name)
            res["update_success"] = False
            return res

        res["ops"] = operations
        used_op = None
        used_loc = {
            "latitude": None,
            "longitude": None,
            "gps_accuracy": None,
            "gps_date": None,
        }

        # Parcourt toutes les opérations et retient la localisation la plus récente
        for op in operations:
            if op["oprnType"] not in ("LOCATION", "LASTLOC", "OFFLINE_LOC"):
                continue

            if "latitude" in op:
                if "extra" in op and "gpsUtcDt" in op["extra"]:
                    utc_date = parse_stf_date(op["extra"]["gpsUtcDt"])
                else:
                    _LOGGER.error(
                        "[%s] Pas de date UTC pour l'opération '%s' : %s",
                        dev_name,
                        op["oprnType"],
                        json.dumps(op),
                    )
                    continue

                if used_loc["gps_date"] and used_loc["gps_date"] >= utc_date:
                    _LOGGER.debug("[%s] Localisation plus ancienne ignorée (%s)", dev_name, op["oprnType"])
                    continue

                used_loc["latitude"] = float(op["latitude"])
                used_loc["longitude"] = float(op["longitude"])
                res["location_found"] = True
                used_loc["gps_accuracy"] = calc_gps_accuracy(
                    op.get("horizontalUncertainty"), op.get("verticalUncertainty")
                )
                used_loc["gps_date"] = utc_date
                used_op = op

            elif "encLocation" in op:
                loc = op["encLocation"]
                if loc.get("encrypted"):
                    _LOGGER.info("[%s] Localisation chiffrée ignorée (%s)", dev_name, op["oprnType"])
                    continue
                if "gpsUtcDt" not in loc:
                    _LOGGER.info("[%s] Localisation sans date ignorée (%s)", dev_name, op["oprnType"])
                    continue

                utc_date = parse_stf_date(loc["gpsUtcDt"])
                if used_loc["gps_date"] and used_loc["gps_date"] >= utc_date:
                    _LOGGER.debug("[%s] Localisation plus ancienne ignorée (%s)", dev_name, op["oprnType"])
                    continue

                if "latitude" in loc and "longitude" in loc:
                    used_loc["latitude"] = float(loc["latitude"])
                    used_loc["longitude"] = float(loc["longitude"])
                    res["location_found"] = True
                else:
                    _LOGGER.warning("[%s] Pas de coordonnées dans '%s'", dev_name, op["oprnType"])

                used_loc["gps_accuracy"] = calc_gps_accuracy(
                    loc.get("horizontalUncertainty"), loc.get("verticalUncertainty")
                )
                used_loc["gps_date"] = utc_date
                used_op = op

        if used_op:
            res["used_op"] = used_op
            res["used_loc"] = used_loc
        else:
            _LOGGER.warning("[%s] Aucune opération de localisation exploitable", dev_name)

        _LOGGER.debug(
            "[%s] Opération retenue : %s",
            dev_name,
            "AUCUNE" if not used_op else used_op["oprnType"],
        )
        return res

    except ConfigEntryAuthFailed:
        raise
    except Exception as err:  # noqa: BLE001
        _LOGGER.error(
            "[%s] Exception lors de la récupération de localisation : %s",
            dev_name,
            err,
            exc_info=True,
        )

    return None


async def async_ring_device(
    session: aiohttp.ClientSession, csrf_token: str, dev_data: dict
) -> bool:
    """Fait sonner l'appareil (opération RING). Retourne True si HTTP 200.

    Nécessite un appareil Galaxy à proximité connecté en Bluetooth. L'arrêt de
    la sonnerie d'un SmartTag n'est pas possible (limitation de l'API).
    """
    ring_payload = {
        "dvceId": dev_data["dvceID"],
        "operation": "RING",
        "usrId": dev_data["usrId"],
        "status": "start",
        "lockMessage": "Home Assistant fait sonner votre appareil !",
    }
    url = f"{URL_ADD_OPERATION}?_csrf={csrf_token}"
    async with session.post(url, json=ring_payload) as response:
        _LOGGER.debug("Réponse sonnerie : statut %s", response.status)
        if response.status == 200:
            _LOGGER.info("Sonnerie envoyée à '%s'", dev_data["modelName"])
            return True
        _LOGGER.error(
            "Échec de la sonnerie pour '%s' (statut %s)",
            dev_data["modelName"],
            response.status,
        )
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def calc_gps_accuracy(hu: float | None, vu: float | None) -> float | None:
    """Précision GPS combinée (théorème de Pythagore) depuis les incertitudes."""
    try:
        return round((float(hu) ** 2 + float(vu) ** 2) ** 0.5, 1)
    except (ValueError, TypeError):
        return None


def get_sub_location(ops: list, sub_device_name: str) -> tuple[dict, dict]:
    """Extrait la sous-localisation (écouteur gauche/droit) d'une opération."""
    if not ops or not sub_device_name:
        return {}, {}
    for op in ops:
        if sub_device_name in op.get("encLocation", {}):
            loc = op["encLocation"][sub_device_name]
            sub_loc = {
                "latitude": float(loc["latitude"]),
                "longitude": float(loc["longitude"]),
                "gps_accuracy": calc_gps_accuracy(
                    loc.get("horizontalUncertainty"), loc.get("verticalUncertainty")
                ),
                "gps_date": parse_stf_date(loc["gpsUtcDt"]),
            }
            return op, sub_loc
    return {}, {}


def parse_stf_date(datestr: str) -> datetime:
    """Convertit une date STF « YYYYMMDDHHmmss » en datetime UTC."""
    return datetime.strptime(datestr, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def get_battery_level(dev_name: str, ops: list) -> int | None:
    """Extrait le niveau de batterie depuis l'opération CHECK_CONNECTION."""
    for op in ops:
        if op["oprnType"] == "CHECK_CONNECTION" and "battery" in op:
            batt_raw = op["battery"]
            batt = BATTERY_LEVELS.get(batt_raw)
            if batt is None:
                try:
                    batt = int(batt_raw)
                except (ValueError, TypeError):
                    _LOGGER.warning("[%s] Niveau de batterie invalide : %s", dev_name, batt_raw)
            return batt
    return None


def gen_qr_code_base64(data: str) -> str:
    """Génère un QR code PNG encodé en base64 (affiché pendant le login)."""
    qr = qrcode.QRCode()
    qr.add_data(data)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
