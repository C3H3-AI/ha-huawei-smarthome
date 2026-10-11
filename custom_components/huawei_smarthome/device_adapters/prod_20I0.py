"""Profile-based adapter for the Huawei Smart Selection OPPLE Lamp Pro (20I0).

The public Profile and Huawei's service-composition model declare the main
lamp's ``switch``, ``brightness`` and ``cct`` services, plus the ``lightMode``
presets.  This adapter intentionally projects those primary lighting
capabilities only.  Study, wake-up, timer, countdown, statistics, backlight,
network and firmware-management services are not part of the basic lamp
projection.

Evidence for the service/field mapping used here:

* ``profileDataHelp`` lists ``20I0`` together with the already-supported
  OPPLE lamps ``2BNN``/``134D``/``101C`` and the rules
  ``switch/on`` and ``brightness/brightness``.
* A packet capture of the official App controlling this exact ``prodId``
  (``20I0``) on the local network carries the service identifiers
  ``switch``, ``brightness``, ``cct`` and ``lightMode``.
* The cloud Profile for ``20I0`` provides the field names, the brightness
  range 3-255, the colour-temperature range 3000-5000 K and five
  ``lightMode`` presets, all of which this adapter reads at runtime rather
  than hard-coding.

Verified on a physical device (model ``MT615-D20WTT``): entity creation,
state read-back, and control of on/off, brightness, colour temperature and the
``lightMode`` presets.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .api import EntitySpec
from .context import DeviceContext


_SWITCH_SID = "switch"
_SWITCH_FIELD = "on"
_BRIGHTNESS_SID = "brightness"
_BRIGHTNESS_FIELD = "brightness"
_CCT_SID = "cct"
_CCT_FIELD = "colorTemperature"
_LIGHT_MODE_SID = "lightMode"
_LIGHT_MODE_FIELD = "mode"


def _field(
    profile: Mapping[str, Any],
    sid: str,
    name: str,
) -> Mapping[str, Any] | None:
    for service in profile.get("services", ()):
        if not isinstance(service, Mapping) or service.get("serviceId") != sid:
            continue
        for field in service.get("characteristics", ()):
            if isinstance(field, Mapping) and field.get("characteristicName") == name:
                return field
    return None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"1", "true", "on"}:
            return True
        if text in {"0", "false", "off"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _range(field: Mapping[str, Any] | None) -> tuple[float, float] | None:
    if field is None:
        return None
    minimum = _number(field.get("min"))
    maximum = _number(field.get("max"))
    if minimum is None or maximum is None or maximum <= minimum:
        return None
    return float(minimum), float(maximum)


def _payload_number(value: Any, field: Mapping[str, Any]) -> int | float:
    number = _number(value)
    if number is None:
        raise ValueError("20I0 value must be numeric")
    if str(field.get("characteristicType") or "").casefold() in {
        "int",
        "integer",
        "enum",
    }:
        return int(round(number))
    return int(number) if float(number).is_integer() else number


def _device_brightness_to_ha(
    value: Any,
    field: Mapping[str, Any],
) -> int | None:
    number = _number(value)
    value_range = _range(field)
    if number is None or value_range is None:
        return None
    minimum, maximum = value_range
    number = min(max(float(number), minimum), maximum)
    return round(1 + (number - minimum) * 254 / (maximum - minimum))


def _ha_brightness_to_device(
    value: Any,
    field: Mapping[str, Any],
) -> int | float:
    number = _number(value)
    value_range = _range(field)
    if number is None or value_range is None:
        raise ValueError("20I0 brightness range is missing from the Profile")
    minimum, maximum = value_range
    number = min(max(float(number), 1), 255)
    return _payload_number(
        minimum + (number - 1) * (maximum - minimum) / 254,
        field,
    )


def _enum_options(field: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    options: list[tuple[str, Any]] = []
    for item in field.get("enumList", ()):
        if not isinstance(item, Mapping) or item.get("enumVal") is None:
            continue
        label = item.get("descCh") or item.get("descEn") or item["enumVal"]
        options.append((str(label), item["enumVal"]))
    return tuple(options)


def _enum_label(field: Mapping[str, Any], value: Any) -> str | None:
    number = _number(value)
    for label, raw in _enum_options(field):
        if number is not None and _number(raw) == number:
            return label
        if str(raw) == str(value):
            return label
    return None


async def _turn_on(context: DeviceContext, data: Mapping[str, Any]) -> None:
    """Turn on first, then apply any requested primary-light values."""

    await context.async_send_service(_SWITCH_SID, {_SWITCH_FIELD: 1})
    profile = context.profile or {}

    brightness = data.get("brightness")
    brightness_field = _field(profile, _BRIGHTNESS_SID, _BRIGHTNESS_FIELD)
    if brightness is not None:
        if brightness_field is None:
            raise ValueError("20I0 brightness field is missing from the Profile")
        await context.async_send_service(
            _BRIGHTNESS_SID,
            {
                _BRIGHTNESS_FIELD: _ha_brightness_to_device(
                    brightness,
                    brightness_field,
                )
            },
        )

    color_temp_kelvin = data.get("color_temp_kelvin")
    cct_field = _field(profile, _CCT_SID, _CCT_FIELD)
    cct_range = _range(cct_field)
    if color_temp_kelvin is not None:
        if cct_field is None or cct_range is None:
            raise ValueError("20I0 color-temperature range is missing from the Profile")
        minimum, maximum = cct_range
        value = min(max(float(color_temp_kelvin), minimum), maximum)
        await context.async_send_service(
            _CCT_SID,
            {_CCT_FIELD: _payload_number(value, cct_field)},
        )


async def _turn_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service(_SWITCH_SID, {_SWITCH_FIELD: 0})


class Product20I0Adapter:
    """Huawei Smart Selection OPPLE Lamp Pro (MT615-D20WTT)."""

    prod_id = "20I0"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        switch = _field(profile, _SWITCH_SID, _SWITCH_FIELD)
        brightness = _field(profile, _BRIGHTNESS_SID, _BRIGHTNESS_FIELD)
        cct = _field(profile, _CCT_SID, _CCT_FIELD)
        brightness_range = _range(brightness)
        cct_range = _range(cct)
        specs: list[EntitySpec] = []

        if switch is not None:
            color_mode = (
                "color_temp"
                if cct_range is not None
                else "brightness"
                if brightness_range is not None
                else "onoff"
            )

            def light_state(device: DeviceContext) -> Mapping[str, Any]:
                return {
                    "is_on": _bool(device.value(_SWITCH_SID, _SWITCH_FIELD)),
                    "brightness": (
                        _device_brightness_to_ha(
                            device.value(_BRIGHTNESS_SID, _BRIGHTNESS_FIELD),
                            brightness or {},
                        )
                        if brightness_range is not None
                        else None
                    ),
                    "color_temp_kelvin": (
                        _number(device.value(_CCT_SID, _CCT_FIELD))
                        if cct_range is not None
                        else None
                    ),
                    "color_mode": color_mode,
                }

            metadata: dict[str, Any] = {
                "supported_color_modes": {color_mode},
            }
            if cct_range is not None:
                metadata["min_color_temp_kelvin"] = int(cct_range[0])
                metadata["max_color_temp_kelvin"] = int(cct_range[1])
            specs.append(
                EntitySpec(
                    platform="light",
                    key="light",
                    name=None,
                    state=light_state,
                    metadata=metadata,
                    actions={"turn_on": _turn_on, "turn_off": _turn_off},
                )
            )

        light_mode = _field(profile, _LIGHT_MODE_SID, _LIGHT_MODE_FIELD)
        options = _enum_options(light_mode) if light_mode is not None else ()
        if light_mode is not None and options:

            async def select_light_mode(
                device: DeviceContext,
                data: Mapping[str, Any],
            ) -> None:
                option = str(data.get("option"))
                for label, raw in options:
                    if label == option:
                        await device.async_send_service(
                            _LIGHT_MODE_SID,
                            {_LIGHT_MODE_FIELD: _payload_number(raw, light_mode)},
                        )
                        return
                raise ValueError(f"20I0 unknown light mode: {option}")

            specs.append(
                EntitySpec(
                    platform="select",
                    key="light_mode",
                    name="灯光模式",
                    state=lambda device: {
                        "current_option": _enum_label(
                            light_mode,
                            device.value(_LIGHT_MODE_SID, _LIGHT_MODE_FIELD),
                        )
                    },
                    metadata={"options": tuple(label for label, _ in options)},
                    actions={"select_option": select_light_mode},
                )
            )

        return tuple(specs)


ADAPTER = Product20I0Adapter()
