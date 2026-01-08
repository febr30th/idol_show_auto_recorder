import json
import os
import sys
from copy import deepcopy
from typing import Any, Dict


class SettingsError(RuntimeError):
    """配置错误（缺文件/缺字段/格式错误等）"""
    pass


def _base_dir() -> str:
    """
    兼容源码运行 / PyInstaller onefile/onedir：
    - 源码运行：以本文件所在目录为基准
    - PyInstaller：以 exe 所在目录为基准（方便在同目录放 settings*.json）
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise SettingsError(f"配置文件不是合法 JSON：{path}\n{e}") from e


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """递归合并 dict：override 覆盖 base（用于 local 覆盖 public）"""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)  # type: ignore[index]
        else:
            base[k] = v


def load_settings() -> Dict[str, Any]:
    """
    加载配置：
    1) settings.json（可提交到 GitHub，无敏感信息）
    2) settings.local.json（本地私有覆盖，不提交）
    """
    base_dir = _base_dir()
    public_path = os.path.join(base_dir, "settings.json")
    local_path = os.path.join(base_dir, "settings.local.json")

    if not os.path.exists(public_path):
        raise SettingsError(
            "未找到 settings.json。\n"
            "请在程序目录下创建 settings.json（可参考仓库提供的默认文件）。"
        )

    cfg = _load_json(public_path)

    if os.path.exists(local_path):
        local_cfg = _load_json(local_path)
        _deep_update(cfg, local_cfg)

    _validate(cfg)
    return cfg


def _require(cfg: Dict[str, Any], path: str) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise SettingsError(f"配置缺失：{path}")
        cur = cur[part]
    return cur


def _validate(cfg: Dict[str, Any]) -> None:
    # 必需字段（用于“能跑起来”的最低门槛）
    _require(cfg, "live48.urls")
    _require(cfg, "target.name")
    _require(cfg, "feishu.app_id")
    _require(cfg, "feishu.app_secret")
    _require(cfg, "feishu.bitable_app_token")
    _require(cfg, "feishu.bitable_table_id")
    _require(cfg, "fields.count")
    _require(cfg, "fields.date")
    _require(cfg, "fields.content")
    _require(cfg, "fields.remark")

    # 值校验（友好报错）
    if not str(cfg["target"]["name"]).strip():
        raise SettingsError("配置错误：target.name 不能为空（请在 settings.local.json 里填写）")

    feishu = cfg.get("feishu", {})
    missing = [k for k in ("app_id", "app_secret", "bitable_app_token", "bitable_table_id") if not str(feishu.get(k, "")).strip()]
    if missing:
        raise SettingsError(
            "飞书配置未完成，请在 settings.local.json 中填写：\n"
            + ", ".join("feishu." + k for k in missing)
        )

    # runtime.interval_hours 可选，默认 6
    rt = cfg.get("runtime", {})
    if "interval_hours" in rt:
        try:
            hours = float(rt["interval_hours"])
            if hours <= 0:
                raise ValueError
        except Exception as e:
            raise SettingsError("runtime.interval_hours 必须是正数（例如 6）") from e
