"""Typed SmartHome discovery and realtime-session API."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote, urlencode

from ..const import (
    CLOUD_ROUTE_SELECT_PATH,
    DEVICE_DETAIL_PATH,
    DEVICE_DYNAMIC_DATA_PATH,
    DEVICE_SNAPSHOT_PATH,
    HOME_SNAPSHOT_PATH,
    MESSAGE_CENTER_LOGIN_PATH,
    SCENE_BY_DEVICE_PATH,
    SCENE_BASE_URL,
    SCENE_DETAIL_V2_PATH,
    SCENE_ENABLED_PATH,
    SCENE_LIST_PATH,
    SCENE_LOGS_PATH,
    SCENE_RUN_EDGE_PATH,
    SCENE_TITLE_PATH,
    SCENE_TYPE_LABELS,
    SMART_HOME_IOS_APP_ID,
    SMART_HOME_USER_AGENT,
)
from ..domain.models import (
    AuthSession,
    MessageChannelSession,
    RemoteDeviceDescriptor,
    RemoteDeviceState,
    RemoteDiscoverySnapshot,
    SmartHomeCloudRoute,
)
from .errors import (
    AuthExpiredError,
    InvalidResponseError,
    PermissionDeniedError,
    RateLimitedError,
    RemoteOperationError,
    TransientNetworkError,
)
from .normalizers import (
    normalize_device_detail,
    normalize_dynamic_states,
    normalize_snapshot,
)
from .transport import AsyncHttpTransport, HttpResponse, UrllibHttpTransport


class SmartHomeDiscoveryApi:
    """HTTP facade for account discovery and device state."""

    def __init__(
        self,
        *,
        transport: AsyncHttpTransport | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._transport = transport or UrllibHttpTransport()
        self._base_url = base_url.rstrip("/") if base_url else None
        self._timeout = timeout

    async def async_get_snapshot(self, session: AuthSession) -> RemoteDiscoverySnapshot:
        """Fetch and normalize the complete homes/devices snapshot."""

        devices = await self._request(session, DEVICE_SNAPSHOT_PATH)
        homes = await self._request(session, HOME_SNAPSHOT_PATH)
        return normalize_snapshot(
            self._json(devices),
            self._json(homes),
        )

    async def async_get_dynamic_states(
        self,
        session: AuthSession,
        devices: Sequence[str],
        *,
        home_id: str | None = None,
    ) -> tuple[RemoteDeviceState, ...]:
        """Fetch the current state for a batch of known devices."""

        device_ids = tuple(dict.fromkeys(device for device in devices if device))
        if not device_ids:
            return ()
        body = json.dumps(
            device_ids,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = await self._request(
            session,
            DEVICE_DYNAMIC_DATA_PATH,
            method="POST",
            body=body,
            extra_headers={
                "Content-Type": "application/json",
                **({"X-HomeId": home_id} if home_id else {}),
            },
        )
        return normalize_dynamic_states(self._json(response))

    async def async_login_message_center(
        self,
        session: AuthSession,
    ) -> MessageChannelSession:
        """Create the ephemeral message-center context for MQTT."""

        if not session.device_id or not session.pushtmid:
            raise InvalidResponseError("SmartHome client identity is unavailable")
        if len(session.pushtmid) != 64:
            raise InvalidResponseError("SmartHome message identity is invalid")
        try:
            int(session.pushtmid, 16)
        except ValueError as error:
            raise InvalidResponseError("SmartHome message identity is invalid") from error
        body = json.dumps(
            {
                "phoneos": "iOS",
                "language": "zh_CN",
                "deviceInfo": {
                    "deviceID": session.device_id,
                    "terminalType": "iphone",
                    "deviceAliasName": session.device_name,
                    "deviceType": "0",
                },
                "pushtmid": session.pushtmid,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        value = self._json(
            await self._request(
                session,
                MESSAGE_CENTER_LOGIN_PATH,
                method="POST",
                body=body,
            )
        )
        if not isinstance(value, Mapping):
            raise InvalidResponseError("message-center response is not an object")
        client_id = value.get("mqttClientId")
        mqtt_topic = value.get("mqttTopic")
        if not isinstance(client_id, str) or not client_id:
            raise InvalidResponseError("message-center response has no client id")
        if not isinstance(mqtt_topic, str) or not mqtt_topic:
            raise InvalidResponseError("message-center response has no topic")
        first_login = value.get("firstLogin")
        log_collection = value.get("logcollection")
        return MessageChannelSession(
            mqtt_client_id=client_id,
            mqtt_topic=mqtt_topic,
            first_login=first_login if isinstance(first_login, bool) else None,
            log_collection=log_collection if isinstance(log_collection, str) else None,
        )

    async def async_select_cloud_route(
        self,
        session: AuthSession,
    ) -> SmartHomeCloudRoute:
        """Resolve the dynamic SmartHome broker route."""

        body = json.dumps(
            {"version": "17.0.3.320", "huid": session.user_id},
            separators=(",", ":"),
        ).encode("utf-8")
        value = self._json(
            await self._request(
                session,
                CLOUD_ROUTE_SELECT_PATH,
                method="POST",
                body=body,
                extra_headers={
                    "huid": session.user_id,
                    "version": "17.0.3.320",
                },
            )
        )
        if not isinstance(value, Mapping):
            raise InvalidResponseError("SmartHome route response is not an object")
        host = value.get("smarthomehost")
        mqtt_port = value.get("mqtts")
        https_port = value.get("https")
        if (
            not isinstance(host, str)
            or not host
            or not isinstance(mqtt_port, int)
            or mqtt_port <= 0
            or not isinstance(https_port, int)
            or https_port <= 0
        ):
            raise InvalidResponseError("SmartHome route response is incomplete")
        expires = value.get("expires")
        role = value.get("role")
        return SmartHomeCloudRoute(
            smart_home_host=host,
            mqtt_port=mqtt_port,
            https_port=https_port,
            expires_seconds=expires if isinstance(expires, int) else None,
            role=role if isinstance(role, int) else None,
        )

    async def async_get_device_detail(
        self,
        session: AuthSession,
        dev_id: str,
    ) -> RemoteDeviceDescriptor:
        """Fetch and normalize one device detail response."""

        if not dev_id:
            raise ValueError("device id is required")
        response = await self._request(
            session,
            DEVICE_DETAIL_PATH.format(dev_id=quote(dev_id, safe="")),
        )
        return normalize_device_detail(self._json(response))

    async def async_get_device_details(
        self,
        session: AuthSession,
        devices: Sequence[str],
        *,
        max_concurrency: int = 8,
    ) -> tuple[RemoteDeviceDescriptor, ...]:
        """Fetch targeted details with bounded concurrency."""

        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch(dev_id: str) -> RemoteDeviceDescriptor | None:
            async with semaphore:
                try:
                    return await self.async_get_device_detail(session, dev_id)
                except AuthExpiredError:
                    raise
                except Exception:
                    return None

        results = await asyncio.gather(*(fetch(dev_id) for dev_id in devices))
        return tuple(device for device in results if device is not None)

    # ------------------------------------------------------------------
    # 场景（Home Automation）
    #
    # 端点路径最初为逆向推断，现已逐服务实测通过（2026-10-13，抓包校准）。
    # 来源：智慧生活 App 17.0.4.312 主体 classes23.dex 反编译出的
    # com.huawei.hiscenario.service.network.NetworkService。
    # 场景 API 使用独立 host（SCENE_BASE_URL），故每次请求覆盖 base_url；
    # 该 host 要求 x-uid（见 _request）。
    # ------------------------------------------------------------------
    async def async_list_scenes(
        self,
        session: AuthSession,
        *,
        need_check: bool = False,
    ) -> tuple[Mapping[str, Any], ...]:
        """列出账号下全部场景（v3，App 当前版本主用）。"""

        response = await self._request(
            session,
            SCENE_LIST_PATH,
            params={"needCheck": str(need_check).lower()},
            base_url=SCENE_BASE_URL,
        )
        return _as_mapping_tuple(scene_payload(self._json(response)))

    async def async_get_scene_detail(
        self,
        session: AuthSession,
        scenario_id: str,
    ) -> Mapping[str, Any]:
        """获取场景详情（触发器 / 条件 / 动作全量）。"""

        if not scenario_id:
            raise ValueError("scenario_id is required")
        response = await self._request(
            session,
            SCENE_DETAIL_V2_PATH.format(scenario_id=quote(scenario_id, safe="")),
            base_url=SCENE_BASE_URL,
        )
        payload = scene_payload(self._json(response))
        return payload if isinstance(payload, Mapping) else {}

    async def async_get_scene_logs(
        self,
        session: AuthSession,
        *,
        cursor: str | None = None,
        page_size: int = 20,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> Mapping[str, Any]:
        """分页查询场景执行日志。"""

        params: dict[str, str] = {"pageSize": str(page_size)}
        if cursor:
            params["cursor"] = cursor
        # 服务端要求 startTime/endTime 必填（抓包验证，毫秒时间戳），缺省取最近 7 天。
        now_ms = int(time.time() * 1000)
        params["startTime"] = start_time or str(now_ms - 7 * 86400_000)
        params["endTime"] = end_time or str(now_ms)
        response = await self._request(
            session, SCENE_LOGS_PATH, params=params, base_url=SCENE_BASE_URL
        )
        payload = scene_payload(self._json(response))
        return payload if isinstance(payload, Mapping) else {}

    async def async_get_scenes_by_device(
        self,
        session: AuthSession,
        device_id: str,
    ) -> tuple[Mapping[str, Any], ...]:
        """按设备 deviceId 查关联场景。"""

        if not device_id:
            raise ValueError("device_id is required")
        response = await self._request(
            session,
            SCENE_BY_DEVICE_PATH,
            params={"deviceId": device_id},
            base_url=SCENE_BASE_URL,
        )
        return _as_mapping_tuple(scene_payload(self._json(response)))

    async def async_run_scene(
        self,
        session: AuthSession,
        scenario_id: str,
    ) -> Any:
        """**手动执行**一次场景。

        抓包验证的 App 真实序列：GET detail 取 ``flow[0].id`` → POST
        ``/v2/applications/{flowId}/edge``，body 里用 manualEvent 触发。
        """

        if not scenario_id:
            raise ValueError("scenario_id is required")
        detail = await self.async_get_scene_detail(session, scenario_id)
        flow_id = _extract_flow_id(detail)
        if not flow_id:
            raise InvalidResponseError("scene detail has no flow id")
        body = json.dumps(
            {
                "extension": {"scenarioId": scenario_id},
                "inputParameter": {
                    "method": "POST",
                    "path": "/run",
                    "body": {"eventType": "huawei.events.manualEvent"},
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = await self._request(
            session,
            SCENE_RUN_EDGE_PATH.format(flow_id=quote(flow_id, safe="")),
            method="POST",
            body=body,
            base_url=SCENE_BASE_URL,
            extra_headers={
                "Content-Type": "application/json; charset=UTF-8",
                "x-edge-path": "run",
            },
        )
        return scene_payload(self._json(response))

    async def async_set_scene_enabled(
        self,
        session: AuthSession,
        scenario_id: str,
        enabled: bool,
    ) -> Any:
        """启用 / 禁用场景。"""

        if not scenario_id:
            raise ValueError("scenario_id is required")
        body = json.dumps(
            {"scenarioId": scenario_id, "enabled": bool(enabled)},
            separators=(",", ":"),
        ).encode("utf-8")
        response = await self._request(
            session,
            SCENE_ENABLED_PATH,
            method="PUT",
            body=body,
            base_url=SCENE_BASE_URL,
        )
        return scene_payload(self._json(response))

    async def async_rename_scene(
        self,
        session: AuthSession,
        scenario_id: str,
        title: str,
    ) -> Any:
        """重命名场景。"""

        if not scenario_id:
            raise ValueError("scenario_id is required")
        body = json.dumps(
            # SceneCard 字段名是 scenarioCardId（抓包+实测验证，scenarioId 会 400 must not be blank）
            {"scenarioCardId": scenario_id, "title": title},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = await self._request(
            session,
            SCENE_TITLE_PATH,
            method="PUT",
            body=body,
            base_url=SCENE_BASE_URL,
        )
        return scene_payload(self._json(response))

    async def _request(
        self,
        session: AuthSession,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        base_url: str | None = None,
    ) -> HttpResponse:
        if not session.hms_access_token:
            raise AuthExpiredError("HMS-lite access token is unavailable")
        origin = base_url or self._base_url or session.base_url
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-Hans-CN;q=1",
            "Authorization": f"Bearer {session.hms_access_token}",
            "X-AppId": SMART_HOME_IOS_APP_ID,
            "X-AppVersion": "17.0.3.320",
            "X-HomeId": "(null)",
            "X-Huid": session.user_id,
            "X-Language": "zh_CN",
            "X-Model": "iPhone",
            "X-Ori-App-Name": SMART_HOME_IOS_APP_ID,
            "X-PhoneOs": "iOS",
            "X-RequestId": str(uuid.uuid4()).upper(),
            "User-Agent": SMART_HOME_USER_AGENT,
        }
        if origin == SCENE_BASE_URL:
            # 场景服务要求 x-uid（抓包验证：缺 x-uid 返回 401 errcode 1002）。
            headers["x-uid"] = session.user_id
        if extra_headers:
            headers.update(extra_headers)
        if body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json;charset=UTF-8"
        response: HttpResponse | None = None
        query = urlencode(params) if params else ""
        url = f"{origin.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"
        for attempt in range(3):
            try:
                response = await self._transport.request(
                    method,
                    url,
                    headers,
                    body,
                    self._timeout,
                )
            except TransientNetworkError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status in {500, 502, 503, 504} and attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            break
        assert response is not None
        if response.status == 401:
            raise AuthExpiredError("SmartHome service session expired")
        if response.status == 403:
            raise PermissionDeniedError("SmartHome access denied")
        if response.status == 429:
            raise RateLimitedError("SmartHome service rate limited the request")
        if response.status >= 400:
            raise RemoteOperationError(f"SmartHome HTTP status {response.status}")
        return response

    @staticmethod
    def _json(response: HttpResponse) -> Any:
        try:
            value = json.loads(response.body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidResponseError("SmartHome response is not JSON") from error
        error_code = _find_error_code(value)
        if error_code in {"200201", "400000021", "400000022", "400000023", "10004"}:
            raise AuthExpiredError("SmartHome service session expired")
        return value


def _find_error_code(value: Any) -> str | None:
    """Read an error code from the response envelope only."""

    if not isinstance(value, Mapping):
        return None
    code = _direct_error_code(value)
    if code is not None:
        return code
    for key in ("error", "errorInfo", "error_info"):
        error = value.get(key)
        if isinstance(error, Mapping):
            code = _direct_error_code(error)
            if code is not None:
                return code
    return None


def _direct_error_code(value: Mapping[str, Any]) -> str | None:
    """Read an error code from one explicitly selected envelope object."""

    for key in ("error_code", "errorCode", "code"):
        candidate = value.get(key)
        if isinstance(candidate, (str, int)):
            return str(candidate)
    return None


def _extract_flow_id(detail: Any) -> str | None:
    """从场景 detail 的 ``flow`` 列表取执行用 flow id（抓包验证）。"""

    if not isinstance(detail, Mapping):
        return None
    flow = detail.get("flow")
    if not isinstance(flow, Sequence) or isinstance(flow, (str, bytes)):
        return None
    for item in flow:
        if isinstance(item, Mapping) and item.get("id"):
            return str(item["id"])
    return None


def scene_payload(value: Any) -> Any:
    """Unwrap the HMS ``Submit<T>`` envelope used by /scenario-manager.

    实测（2026-10-13）：成功壳为 ``{"code":0,"message":"success",...}``，实参可能在
    ``payload`` / ``data`` 层，也可能直接平铺（如 edge 执行返回 ``result:{}``）；
    ``status`` / ``code`` 为 0、缺失或 200 视为成功，非 0 抛错。
    """

    if not isinstance(value, Mapping):
        return value
    status = value.get("status", value.get("code", 0))
    if status not in (0, "0", None, 200, "200"):
        raise RemoteOperationError(
            "SmartHome scene service returned status "
            f"{status}: {str(value.get('errorMsg') or value.get('message') or value)[:160]}"
        )
    for key in ("payload", "data"):
        if key in value:
            return value[key]
    return value


def _as_mapping_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Coerce a scene payload into a tuple of mappings."""

    if isinstance(value, Mapping):
        # 个别端点把列表塞在内层键里
        for key in ("scenarios", "list", "items", "scenarioCards"):
            inner = value.get(key)
            if isinstance(inner, Sequence) and not isinstance(inner, (str, bytes)):
                return tuple(item for item in inner if isinstance(item, Mapping))
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def scene_brief_to_entity(item: Mapping[str, Any]) -> dict[str, Any]:
    """压缩 ``ScenarioBrief`` 成服务响应用的精简结构。"""

    scene_type = item.get("type")
    return {
        "scenario_id": item.get("scenarioId") or item.get("scenarioCardId") or "",
        "title": item.get("title") or item.get("name") or "",
        "enabled": bool(item.get("status", item.get("enabled", False))),
        "type": scene_type,
        "type_label": SCENE_TYPE_LABELS.get(scene_type, "未知")
        if isinstance(scene_type, int)
        else "未知",
        "home_id": item.get("homeId") or "",
        "room_name": item.get("roomName") or "",
        "is_template": bool(item.get("isTemplate", False)),
    }
