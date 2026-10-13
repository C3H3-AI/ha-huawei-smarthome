"""Huawei SmartHome 服务。

目前只有一组：**智慧生活场景**（Home Automation）。

⚠️ 全部端点为**逆向推断，未实机验证**。
来源：智慧生活 App 17.0.4.312 主体 ``classes23.dex`` 反编译出的
``com.huawei.hiscenario.service.network.NetworkService``（HMS ``Submit<T>`` 注解接口）。
这些端点与本集成的设备发现接口同 host（``smarthome.hicloud.com``），
认证同样走 HMS-lite access token。

如果实机返回非 0 状态，请带上抓包反馈，字段名即可据此校准。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import SupportsResponse

from .api.client import scene_brief_to_entity
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

_LOGGER = logging.getLogger(__name__)

SERVICE_LIST_SCENES = "list_scenes"
SERVICE_SCENE_DETAIL = "scene_detail"
SERVICE_RUN_SCENE = "run_scene"
SERVICE_SCENE_SET_ENABLED = "scene_set_enabled"
SERVICE_SCENE_RENAME = "scene_rename"
SERVICE_SCENE_LOGS = "scene_logs"
SERVICE_SCENES_BY_DEVICE = "scenes_by_device"

SCENE_SERVICES = (
    SERVICE_LIST_SCENES,
    SERVICE_SCENE_DETAIL,
    SERVICE_RUN_SCENE,
    SERVICE_SCENE_SET_ENABLED,
    SERVICE_SCENE_RENAME,
    SERVICE_SCENE_LOGS,
    SERVICE_SCENES_BY_DEVICE,
)


async def async_register_services(hass: "HomeAssistant") -> None:
    """注册服务（幂等，可重复调用）。"""

    if hass.services.has_service(DOMAIN, SERVICE_LIST_SCENES):
        return

    def _resolve(entry_id: str | None) -> tuple[Any | None, dict[str, Any] | None]:
        """取出一个已配置条目的 runtime 客户端。

        本集成用 ``entry.runtime_data``（不是 ``hass.data[DOMAIN]``），
        故走 config_entries 列表解析。
        """

        entries = [
            item
            for item in hass.config_entries.async_loaded_entries(DOMAIN)
            if getattr(item, "runtime_data", None) is not None
        ]
        if entry_id:
            target = next((e for e in entries if e.entry_id == entry_id), None)
        else:
            target = entries[0] if entries else None
        if target is None:
            return None, {"ok": False, "error": "没有可用的配置条目"}
        return target.runtime_data, None

    async def _call_scene(
        call: "ServiceCall",
        action: str,
        invoke: Any,
    ) -> "ServiceResponse":
        """统一的场景调用外壳：取客户端 → 调 API → 兜住异常。"""

        runtime, err = _resolve(call.data.get("entry_id"))
        if err:
            return err
        try:
            session = await runtime.async_get_session()
            result = await invoke(runtime, session)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("场景操作 %s 失败: %s", action, exc)
            return {"ok": False, "action": action, "error": str(exc)}
        return {"ok": True, "action": action, "result": result}

    async def _list_scenes(call: "ServiceCall") -> "ServiceResponse":
        """列出账号下全部场景。"""

        async def invoke(runtime: Any, session: Any) -> Any:
            scenes = await runtime.api.async_list_scenes(
                session, need_check=bool(call.data.get("need_check", False))
            )
            items = [scene_brief_to_entity(item) for item in scenes]
            return {"count": len(items), "scenes": items}

        return await _call_scene(call, SERVICE_LIST_SCENES, invoke)

    async def _scene_detail(call: "ServiceCall") -> "ServiceResponse":
        """场景详情（触发器 / 条件 / 动作全量）。"""

        scenario_id = call.data["scenario_id"]

        async def invoke(runtime: Any, session: Any) -> Any:
            return await runtime.api.async_get_scene_detail(session, scenario_id)

        return await _call_scene(call, SERVICE_SCENE_DETAIL, invoke)

    async def _run_scene(call: "ServiceCall") -> "ServiceResponse":
        """⚠️ 立即执行一次场景。"""

        scenario_id = call.data["scenario_id"]
        _LOGGER.warning("收到 run_scene 服务调用：将立即执行场景 %s", scenario_id)

        async def invoke(runtime: Any, session: Any) -> Any:
            return await runtime.api.async_run_scene(session, scenario_id)

        return await _call_scene(call, SERVICE_RUN_SCENE, invoke)

    async def _scene_set_enabled(call: "ServiceCall") -> "ServiceResponse":
        """启用 / 禁用场景。"""

        scenario_id = call.data["scenario_id"]
        enabled = bool(call.data["enabled"])

        async def invoke(runtime: Any, session: Any) -> Any:
            return await runtime.api.async_set_scene_enabled(
                session, scenario_id, enabled
            )

        response = await _call_scene(call, SERVICE_SCENE_SET_ENABLED, invoke)
        if response.get("ok"):
            response["enabled"] = enabled
        return response

    async def _scene_rename(call: "ServiceCall") -> "ServiceResponse":
        """重命名场景。"""

        scenario_id = call.data["scenario_id"]
        title = call.data["title"]

        async def invoke(runtime: Any, session: Any) -> Any:
            return await runtime.api.async_rename_scene(session, scenario_id, title)

        return await _call_scene(call, SERVICE_SCENE_RENAME, invoke)

    async def _scene_logs(call: "ServiceCall") -> "ServiceResponse":
        """分页查询场景执行日志。"""

        async def invoke(runtime: Any, session: Any) -> Any:
            return await runtime.api.async_get_scene_logs(
                session,
                cursor=call.data.get("cursor"),
                page_size=int(call.data.get("page_size", 20)),
                start_time=call.data.get("start_time"),
                end_time=call.data.get("end_time"),
            )

        return await _call_scene(call, SERVICE_SCENE_LOGS, invoke)

    async def _scenes_by_device(call: "ServiceCall") -> "ServiceResponse":
        """按设备 deviceId 查关联场景。"""

        device_id = call.data["device_id"]

        async def invoke(runtime: Any, session: Any) -> Any:
            scenes = await runtime.api.async_get_scenes_by_device(session, device_id)
            items = [scene_brief_to_entity(item) for item in scenes]
            return {"count": len(items), "scenes": items}

        return await _call_scene(call, SERVICE_SCENES_BY_DEVICE, invoke)

    entry_field = {vol.Optional("entry_id"): str}
    scenario_id_field = {vol.Required("scenario_id"): str}

    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_SCENES,
        _list_scenes,
        schema=vol.Schema({**entry_field, vol.Optional("need_check"): bool}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCENE_DETAIL,
        _scene_detail,
        schema=vol.Schema({**entry_field, **scenario_id_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_SCENE,
        _run_scene,
        schema=vol.Schema({**entry_field, **scenario_id_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCENE_SET_ENABLED,
        _scene_set_enabled,
        schema=vol.Schema(
            {**entry_field, **scenario_id_field, vol.Required("enabled"): bool}
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCENE_RENAME,
        _scene_rename,
        schema=vol.Schema(
            {**entry_field, **scenario_id_field, vol.Required("title"): str}
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCENE_LOGS,
        _scene_logs,
        schema=vol.Schema(
            {
                **entry_field,
                vol.Optional("cursor"): str,
                vol.Optional("page_size", default=20): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional("start_time"): str,
                vol.Optional("end_time"): str,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCENES_BY_DEVICE,
        _scenes_by_device,
        schema=vol.Schema({**entry_field, vol.Required("device_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )

    _LOGGER.debug("已注册 %d 个场景服务", len(SCENE_SERVICES))
