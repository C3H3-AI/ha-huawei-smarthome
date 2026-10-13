"""Constants for the Huawei SmartHome integration."""

from __future__ import annotations

DOMAIN = "huawei_smarthome"
MANUFACTURER = "Huawei SmartHome"

CONF_ACCOUNT = "account"
CONF_USER_ID = "user_id"
CONF_IDENTITY_FINGERPRINT = "identity_fingerprint"
CONF_SELECTED_HOME_IDS = "selected_home_ids"
CONF_PASSWORD = "password"

IDENTITY_STORAGE_KEY = "huawei_smarthome/device_identity.json"
ACCOUNT_STORAGE_PREFIX = "huawei_smarthome/accounts"
STATE_STORAGE_PREFIX = "huawei_smarthome"

SMART_HOME_APP_ID = "com.huawei.smarthome"
SMART_HOME_IOS_APP_ID = "com.huawei.smarthome-ios"
SMART_HOME_OAUTH_CLIENT_ID = "10406921"
SMART_HOME_ACCOUNT_VERSION = "69100"
SMART_HOME_ACCOUNT_CLIENT_VERSION = "ios_HwID_6.10.0.300"
SMART_HOME_ACCOUNT_USER_AGENT = (
    "SmartHome/17.0.3.320 CFNetwork/1335.0.3.4 Darwin/21.6.0"
)
SMART_HOME_USER_AGENT = "SmartHome/1.0.842 (iPhone; iOS 15.8.8; Scale/2.00)"

ACCOUNT_BASE_URL = "https://hwid-drcn.platform.hicloud.com"
OAUTH_BASE_URL = "https://oauth-login.platform.hicloud.com"
SMART_HOME_BASE_URL = "https://smarthome.hicloud.com"
PROFILE_CDN_BASE_URL = "https://smarthome-drcn.dbankcdn.com"
PROFILE_CDN_PATH = "/device/guide/{prod_id}/{prod_id}.json"

DEVICE_SNAPSHOT_PATH = "/smart-life/v5/devices/info"
DEVICE_DYNAMIC_DATA_PATH = "/smart-life/v5/devices/dynamic/data"
HOME_SNAPSHOT_PATH = "/smart-life/v5/homes"
DEVICE_DETAIL_PATH = "/smart-life/v2/devices/{dev_id}"
MESSAGE_CENTER_LOGIN_PATH = "/message-center/v1/login"
CLOUD_ROUTE_SELECT_PATH = "/trs/v1/app/route/select"
HMS_LITE_TOKEN_PATH = "/smart-life/v2/hms-lite/token"

# ---------------------------------------------------------------------------
# 场景（Home Automation）
#
# ⚠️ 以下端点全部为**逆向推断，未实机验证**。
# 来源：智慧生活 App 17.0.4.312 主体 classes23.dex 反编译出的
# com.huawei.hiscenario.service.network.NetworkService（HMS ``Submit<T>`` 注解接口），
# 同一 host（该接口里也有本集成在用的 /smart-life/v3/devices）。
#
# 该接口里 ``Submit<T>`` 的 ``T`` 是 HMS SDK 的响应壳，实参在 ``payload`` 字段，
# 故统一走 scene_payload() 解包。
# ---------------------------------------------------------------------------
SCENE_BASE_PATH = "/scenario-manager"
SCENE_LIST_PATH = f"{SCENE_BASE_PATH}/v3/scenarios"          # GET，App 当前主用
SCENE_LIST_V2_PATH = f"{SCENE_BASE_PATH}/v2/scenarios"       # GET，兜底
SCENE_DETAIL_PATH = f"{SCENE_BASE_PATH}/v1/scenarios/{{scenario_id}}"
SCENE_DETAIL_V2_PATH = f"{SCENE_BASE_PATH}/v2/scenarios/{{scenario_id}}"
SCENE_ENABLED_PATH = f"{SCENE_BASE_PATH}/v1/scenarios/enabled"      # PUT
SCENE_TITLE_PATH = f"{SCENE_BASE_PATH}/v1/scenarios/title"          # PUT
SCENE_BASIC_PATH = f"{SCENE_BASE_PATH}/v1/scenarios/basic"          # PUT
SCENE_LOGS_PATH = f"{SCENE_BASE_PATH}/v3/scenarios/logs"            # GET，执行日志
SCENE_SIMULATE_PATH = f"{SCENE_BASE_PATH}/v1/template/simulate"     # POST，手动执行
SCENE_BY_DEVICE_PATH = f"{SCENE_BASE_PATH}/v3/scenariosByDeviceId"  # GET

#: ``ScenarioBrief.type`` 取值（反编译自 hiscenario 常量）
SCENE_TYPE_LABELS: dict[int, str] = {
    0: "混合",
    1: "手动",
    2: "面板",
    3: "自动",
    4: "分隔线",
    5: "AIGC",
    7: "模拟点击",
    8: "房间折叠",
    9: "空间主题",
}

OBSERVED_MQTT_PORT = 8883
OBSERVED_MQTT_SUBSCRIPTION_QOS = 2
OBSERVED_MQTT_FILTER = "/smartHome/signaltrans/v2/categories/command"
PLATFORMS = (
    "light",
    "switch",
    "sensor",
    "select",
    "number",
    "fan",
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "event",
    "humidifier",
    "water_heater",
    "lock",
    "media_player",
    "text",
)
UNASSIGNED_HOME_ID = "__unassigned__"

# HuaweiHome Bridge registers HA entities in Huawei IoT with these virtual
# product IDs.  Importing them here would feed the same entities back into HA.
HWHOMEBRIDGE_PROD_IDS = frozenset(
    {
        "9MTJ",
        "9MTL",
        "9MTM",
        "9MTR",
        "9MTV",
        "9MTW",
        "9MTX",
        "9MU7",
        "ZG37",
    }
)
