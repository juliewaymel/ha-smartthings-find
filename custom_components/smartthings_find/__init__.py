"""Intégration SmartThings Find pour Home Assistant.

Suivi et sonnerie des appareils Samsung Galaxy (téléphones, montres, écouteurs,
SmartTags) via l'API non officielle SmartThings Find.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import STFConfigEntry, SmartThingsFindCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: STFConfigEntry) -> bool:
    """Configure SmartThings Find depuis une entrée de configuration."""
    coordinator = SmartThingsFindCoordinator(hass, entry)

    # Authentifie la session et charge les appareils (lève ConfigEntryAuthFailed
    # si le cookie a expiré -> HA propose la ré-authentification par QR)
    await coordinator.async_setup()

    # Premier rafraîchissement : ne marque l'intégration « chargée » qu'en cas de
    # succès (peut prendre 10-15 s selon le nombre d'appareils)
    await coordinator.async_config_entry_first_refresh()

    # HA >= 2024.6 : on transporte le coordinateur dans l'entrée elle-même
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Recharge l'intégration quand les options changent
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: STFConfigEntry) -> bool:
    """Décharge une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: STFConfigEntry) -> None:
    """Recharge l'entrée après une modification des options."""
    await hass.config_entries.async_reload(entry.entry_id)
