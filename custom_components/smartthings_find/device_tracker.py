"""Suivi de position (device_tracker) pour SmartThings Find."""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import get_battery_level, get_sub_location
from .const import SUBTYPE_EARBUDS
from .coordinator import STFConfigEntry, SmartThingsFindCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: STFConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les entités device_tracker."""
    coordinator = entry.runtime_data
    entities: list[SmartThingsDeviceTracker] = []
    for device in coordinator.devices:
        data = device["data"]
        # Écouteurs (CANAL2) : une entité par oreillette + une entité globale
        if data.get("subType") == SUBTYPE_EARBUDS:
            entities.append(SmartThingsDeviceTracker(coordinator, device, "left"))
            entities.append(SmartThingsDeviceTracker(coordinator, device, "right"))
        entities.append(SmartThingsDeviceTracker(coordinator, device))
    async_add_entities(entities)


class SmartThingsDeviceTracker(CoordinatorEntity[SmartThingsFindCoordinator], TrackerEntity):
    """Suivi de position d'un appareil SmartThings Find."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartThingsFindCoordinator,
        device: dict,
        sub_device_name: str | None = None,
    ) -> None:
        """Initialise le tracker."""
        super().__init__(coordinator)
        self.device = device["data"]
        self.device_id = self.device["dvceID"]
        self.sub_device_name = sub_device_name

        suffix = f"_{sub_device_name}" if sub_device_name else ""
        self._attr_unique_id = f"stf_device_tracker_{self.device_id}{suffix}"
        # Entité principale : nom = celui de l'appareil ; oreillettes : "Left"/"Right"
        self._attr_name = sub_device_name.capitalize() if sub_device_name else None
        self._attr_device_info = device["ha_dev_info"]

        icons = self.device.get("icons", {})
        if "coloredIcon" in icons:
            self._attr_entity_picture = icons["coloredIcon"]

    @property
    def _tag_data(self) -> dict:
        """Données de localisation courantes pour cet appareil."""
        return self.coordinator.data.get(self.device_id) or {}

    @property
    def available(self) -> bool:
        """Disponible si le dernier rafraîchissement de l'appareil a réussi."""
        if not super().available:
            return False
        tag_data = self._tag_data
        return bool(tag_data) and tag_data.get("update_success", False)

    @property
    def source_type(self) -> SourceType:
        """Type de source de localisation."""
        return SourceType.GPS

    def _resolved_loc(self) -> dict:
        """Retourne le dict de localisation (globale ou sous-appareil)."""
        tag_data = self._tag_data
        if self.sub_device_name:
            _, loc = get_sub_location(tag_data.get("ops", []), self.sub_device_name)
            return loc or {}
        if tag_data.get("location_found"):
            return tag_data.get("used_loc") or {}
        return {}

    @property
    def latitude(self) -> float | None:
        """Latitude de l'appareil."""
        return self._resolved_loc().get("latitude")

    @property
    def longitude(self) -> float | None:
        """Longitude de l'appareil."""
        return self._resolved_loc().get("longitude")

    @property
    def location_accuracy(self) -> float | None:
        """Précision GPS."""
        return self._resolved_loc().get("gps_accuracy") or 0

    @property
    def battery_level(self) -> int | None:
        """Niveau de batterie (non pertinent pour les sous-appareils)."""
        if self.sub_device_name:
            return None
        return get_battery_level(self.name or self.device_id, self._tag_data.get("ops", []))

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires (dont la date de dernière position)."""
        tag_data = dict(self._tag_data)
        if self.sub_device_name:
            used_op, used_loc = get_sub_location(
                tag_data.get("ops", []), self.sub_device_name
            )
            tag_data = tag_data | used_op | used_loc
        used_loc = tag_data.get("used_loc") or {}
        tag_data["last_seen"] = used_loc.get("gps_date")
        return tag_data | self.device
