#!/usr/bin/env python3
"""
删除 Claude Code 中的 Langfuse 环境变量配置。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collector import CollectorConfig, refresh_config


def read_settings(config: CollectorConfig) -> Dict[str, Any]:
    try:
        settings_file = config.get_settings_file()
        if not settings_file.exists():
            return {}
        return json.loads(settings_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_settings(config: CollectorConfig, data: Dict[str, Any]) -> None:
    settings_file = config.get_settings_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    config = refresh_config()
    settings = read_settings(config)
    env = dict(settings.get("env") or {})

    for key in CollectorConfig.REMOVE_KEYS:
        env.pop(key, None)

    settings["env"] = env
    write_settings(config, settings)

    print(f"已从 {config.get_settings_file()} 中移除 Langfuse 环境变量")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
