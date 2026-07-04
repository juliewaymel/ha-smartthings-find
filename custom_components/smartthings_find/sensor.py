"""Capteur de batterie pour SmartThings Find."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import get_battery_level
from .coordinator import STFConfigEntry, SmartThingsFindCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: STFConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les capteurs de batterie."""
    coordinator = entry.runtime_data
    async_add_entities(
        DeviceBatterySensor(coordinator, device) for device in coordinator.devices
    )


class DeviceBatterySensor(
    CoordinatorEntity[SmartThingsFindCoordinator], SensorEntity
):
    """Capteur de niveau de batterie d'un appareil."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self, coordinator: SmartThingsFindCoordinator, device: dict
    ) -> None:
        """Initialise le capteur."""
        super().__init__(coordinator)
        self.device = device["data"]
        self.device_id = self.device["dvceID"]
        self._attr_unique_id = f"stf_device_battery_{self.device_id}"
        self._attr_device_info = device["ha_dev_info"]

    @property
    def _tag_data(self) -> dict:
        """Données courantes pour cet appareil."""
        return self.coordinator.data.get(self.device_id) or {}

    @property
    def available(self) -> bool:
        """Disponible si le dernier rafraîchissement a réussi."""
        if not super().available:
            return False
        tag_data = self._tag_data
        return bool(tag_data) and tag_data.get("update_success", False)

    @property
    def native_value(self) -> int | None:
        """Niveau de batterie courant."""
        return get_battery_level(self.device_id, self._tag_data.get("ops", []))
