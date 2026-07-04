"""Flux de configuration (login QR) pour SmartThings Find."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .api import do_login_stage_one, do_login_stage_two, gen_qr_code_base64
from .const import (
    CONF_ACTIVE_MODE_OTHERS,
    CONF_ACTIVE_MODE_OTHERS_DEFAULT,
    CONF_ACTIVE_MODE_SMARTTAGS,
    CONF_ACTIVE_MODE_SMARTTAGS_DEFAULT,
    CONF_JSESSIONID,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_DEFAULT,
    CONF_UPDATE_INTERVAL_MIN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SmartThingsFindConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration de SmartThings Find."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise l'état du flux."""
        self._reauth_entry: ConfigEntry | None = None
        self._task_stage_one: asyncio.Task | None = None
        self._task_stage_two: asyncio.Task | None = None
        self._session = None
        self._qr_url: str | None = None
        self._jsessionid: str | None = None
        self._error: str | None = None

    async def _do_stage_one(self) -> None:
        """Tâche de fond : étape 1 du login (récupère l'URL du QR)."""
        _LOGGER.debug("Login étape 1")
        try:
            stage_one_res = await do_login_stage_one(self.hass)
            if stage_one_res is not None:
                self._session, self._qr_url = stage_one_res
            else:
                self._error = "stage_one_failed"
                _LOGGER.warning("Login étape 1 échouée")
        except Exception as err:  # noqa: BLE001
            self._error = "stage_one_failed"
            _LOGGER.error("Exception étape 1 : %s", err, exc_info=True)

    async def _do_stage_two(self) -> None:
        """Tâche de fond : étape 2 du login (attend le scan, récupère JSESSIONID)."""
        _LOGGER.debug("Login étape 2")
        try:
            stage_two_res = await do_login_stage_two(self._session)
            if stage_two_res is not None:
                self._jsessionid = stage_two_res
                _LOGGER.info("Login réussi")
            else:
                self._error = "stage_two_failed"
                _LOGGER.warning("Login étape 2 échouée")
        except Exception as err:  # noqa: BLE001
            self._error = "stage_two_failed"
            _LOGGER.error("Exception étape 2 : %s", err, exc_info=True)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Première étape : prépare la session et l'URL du QR code."""
        if not self._task_stage_one:
            self._task_stage_one = self.hass.async_create_task(self._do_stage_one())
        if not self._task_stage_one.done():
            return self.async_show_progress(
                step_id="user",
                progress_action="task_stage_one",
                progress_task=self._task_stage_one,
            )
        if self._error:
            return self.async_show_progress_done(next_step_id="finish")
        return self.async_show_progress_done(next_step_id="auth_stage_two")

    async def async_step_auth_stage_two(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Deuxième étape : affiche le QR et attend le scan côté Galaxy."""
        if not self._task_stage_two:
            self._task_stage_two = self.hass.async_create_task(self._do_stage_two())
        if not self._task_stage_two.done():
            return self.async_show_progress(
                step_id="auth_stage_two",
                progress_action="task_stage_two",
                progress_task=self._task_stage_two,
                description_placeholders={
                    "qr_code": gen_qr_code_base64(self._qr_url),
                    "url": self._qr_url,
                    "code": self._qr_url.split("/")[-1],
                },
            )
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape finale : crée (ou met à jour) l'entrée, ou affiche l'erreur."""
        if self._error:
            return self.async_show_form(
                step_id="finish", errors={"base": self._error}
            )

        data = {CONF_JSESSIONID: self._jsessionid}

        if self._reauth_entry:
            return self.async_update_reload_and_abort(self._reauth_entry, data=data)

        return self.async_create_entry(title="SmartThings Find", data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Démarre la ré-authentification (session expirée)."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirmation avant de relancer le login QR."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=vol.Schema({})
            )
        # Réinitialise les tâches puis relance le flux de login
        self._task_stage_one = None
        self._task_stage_two = None
        self._error = None
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Crée le flux d'options."""
        return SmartThingsFindOptionsFlowHandler()


class SmartThingsFindOptionsFlowHandler(OptionsFlow):
    """Gère le flux d'options (intervalle, modes actifs)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Affiche/enregistre les options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(
                        CONF_UPDATE_INTERVAL, CONF_UPDATE_INTERVAL_DEFAULT
                    ),
                ): vol.All(vol.Coerce(int), vol.Clamp(min=CONF_UPDATE_INTERVAL_MIN)),
                vol.Optional(
                    CONF_ACTIVE_MODE_SMARTTAGS,
                    default=options.get(
                        CONF_ACTIVE_MODE_SMARTTAGS, CONF_ACTIVE_MODE_SMARTTAGS_DEFAULT
                    ),
                ): bool,
                vol.Optional(
                    CONF_ACTIVE_MODE_OTHERS,
                    default=options.get(
                        CONF_ACTIVE_MODE_OTHERS, CONF_ACTIVE_MODE_OTHERS_DEFAULT
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
