"""Bouton « faire sonner » pour SmartThings Find."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import async_ring_device
from .coordinator import STFConfigEntry, SmartThingsFindCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: STFConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les boutons de sonnerie."""
    coordinator = entry.runtime_data
    async_add_entities(
        RingButton(coordinator, device) for device in coordinator.devices
    )


class RingButton(ButtonEntity):
    """Bouton faisant sonner un appareil SmartThings Find."""

    _attr_has_entity_name = True
    _attr_translation_key = "ring"
    _attr_icon = "mdi:nfc-search-variant"

    def __init__(
        self, coordinator: SmartThingsFindCoordinator, device: dict
    ) -> None:
        """Initialise le bouton."""
        self._coordinator = coordinator
        self.device = device["data"]
        self._attr_unique_id = f"stf_ring_button_{self.device['dvceID']}"
        self._attr_device_info = device["ha_dev_info"]

        icons = self.device.get("icons", {})
        if "coloredIcon" in icons:
            self._attr_entity_picture = icons["coloredIcon"]

    async def async_press(self) -> None:
        """Déclenche la sonnerie de l'appareil."""
        coordinator = self._coordinator
        try:
            ok = await async_ring_device(
                coordinator.session, coordinator.csrf_token, self.device
            )
            if not ok:
                # Échec : rafraîchit le _csrf au cas où la session aurait tourné
                await coordinator.async_refresh_csrf()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Exception lors de la sonnerie de '%s' : %s",
                self.device["modelName"],
                err,
            )
