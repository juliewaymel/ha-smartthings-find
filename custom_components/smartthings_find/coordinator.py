"""DataUpdateCoordinator pour SmartThings Find."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import fetch_csrf, get_device_location, get_devices
from .const import (
    CONF_ACTIVE_MODE_OTHERS,
    CONF_ACTIVE_MODE_OTHERS_DEFAULT,
    CONF_ACTIVE_MODE_SMARTTAGS,
    CONF_ACTIVE_MODE_SMARTTAGS_DEFAULT,
    CONF_JSESSIONID,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_DEFAULT,
    DEVICE_TYPE_TAG,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Alias typé : l'entrée de config transporte son coordinateur (HA >= 2024.6)
type STFConfigEntry = ConfigEntry["SmartThingsFindCoordinator"]


class SmartThingsFindCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gère la récupération périodique des données SmartThings Find.

    L'état (session, cookie, jeton _csrf, liste d'appareils, modes actifs) est
    porté par le coordinateur lui-même — plus par `hass.data` comme dans le
    dépôt source. C'est la principale modernisation structurelle.
    """

    config_entry: STFConfigEntry

    def __init__(self, hass: HomeAssistant, entry: STFConfigEntry) -> None:
        """Initialise le coordinateur."""
        self.session = async_get_clientsession(hass)
        self.jsessionid: str = entry.data[CONF_JSESSIONID]
        self.csrf_token: str | None = None
        self.devices: list[dict] = []

        self.active_smarttags: bool = entry.options.get(
            CONF_ACTIVE_MODE_SMARTTAGS, CONF_ACTIVE_MODE_SMARTTAGS_DEFAULT
        )
        self.active_others: bool = entry.options.get(
            CONF_ACTIVE_MODE_OTHERS, CONF_ACTIVE_MODE_OTHERS_DEFAULT
        )
        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL, CONF_UPDATE_INTERVAL_DEFAULT
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def async_setup(self) -> None:
        """Authentifie la session et charge la liste des appareils.

        Appelé une fois avant le premier rafraîchissement. Lève
        ConfigEntryAuthFailed si le cookie n'est plus valable (-> reauth).
        """
        # Injecte le cookie JSESSIONID stocké dans l'entrée de config
        self.session.cookie_jar.update_cookies({"JSESSIONID": self.jsessionid})
        # fetch_csrf lève ConfigEntryAuthFailed si l'auth a échoué
        self.csrf_token = await fetch_csrf(self.session)
        self.devices = await get_devices(self.hass, self.session, self.csrf_token)

    async def async_refresh_csrf(self) -> None:
        """Rafraîchit le jeton _csrf (utilisé après un échec ponctuel)."""
        self.csrf_token = await fetch_csrf(self.session)

    def is_active_for(self, dev_data: dict) -> bool:
        """Indique si le mode actif s'applique à cet appareil."""
        if dev_data.get("deviceTypeCode") == DEVICE_TYPE_TAG:
            return self.active_smarttags
        return self.active_others

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère la localisation de tous les appareils."""
        try:
            if self.csrf_token is None:
                await self.async_refresh_csrf()

            tags: dict[str, Any] = {}
            _LOGGER.debug("Mise à jour des localisations...")
            for device in self.devices:
                dev_data = device["data"]
                tag_data = await get_device_location(
                    self.session,
                    self.csrf_token,
                    dev_data,
                    self.is_active_for(dev_data),
                )
                tags[dev_data["dvceID"]] = tag_data
            _LOGGER.debug("%d localisations récupérées", len(tags))
            return tags
        except ConfigEntryAuthFailed:
            # Propagée telle quelle : HA déclenchera le flux de ré-authentification
            raise
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Erreur de récupération des données : {err}") from err
