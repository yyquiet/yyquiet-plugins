#!/usr/bin/env python3
"""
交互式写入 Claude Code 所需的 Langfuse 环境变量。
"""

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="写入 Langfuse 环境变量")
    parser.add_argument("--public-key", dest="public_key")
    parser.add_argument("--secret-key", dest="secret_key")
    parser.add_argument("--base-url", dest="base_url")
    return parser.parse_args()


def main() -> int:
    config = refresh_config()
    args = parse_args()

    print("==> 配置 Langfuse 环境变量...")

    public_key = args.public_key
    secret_key = args.secret_key
    base_url = args.base_url

    if not public_key or not secret_key or not base_url:
        print("必须提供 public key、secret key 和 base URL。")
        return 1

    settings = read_settings(config)
    env = dict(settings.get("env") or {})
    env.update(
        {
            CollectorConfig.TRACE_TO_LANGFUSE: "true",
            CollectorConfig.LANGFUSE_PUBLIC_KEY: public_key,
            CollectorConfig.LANGFUSE_SECRET_KEY: secret_key,
            CollectorConfig.LANGFUSE_BASE_URL: base_url,
        }
    )
    settings["env"] = env
    write_settings(config, settings)

    print(f"已写入配置到 {config.get_settings_file()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
