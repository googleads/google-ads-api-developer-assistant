#!/usr/bin/env python3
"""Top-level helper script to configure Google Ads API financial transaction upper limits."""

from importlib.util import module_from_spec, spec_from_file_location
import os
import sys


def _load_impl():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(
            os.path.join(
                this_dir,
                "plugins/google-ads-api-developer-assistant/skills/execute-mutation/scripts/set_financial_limits.py",
            )
        ),
        os.path.abspath(
            os.path.join(
                this_dir,
                "skills/execute-mutation/scripts/set_financial_limits.py",
            )
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/skills/execute-mutation/scripts/set_financial_limits.py"
        ),
    ]
    for path in candidates:
        if os.path.isfile(path):
            spec = spec_from_file_location("set_financial_limits", path)
            if spec and spec.loader:
                mod = module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    raise FileNotFoundError("Could not locate set_financial_limits.py implementation.")


_MOD = _load_impl()
FINANCIAL_LIMITS_FILENAME = _MOD.FINANCIAL_LIMITS_FILENAME
FINANCIAL_LIMIT_SPECS = _MOD.FINANCIAL_LIMIT_SPECS
LIMIT_KEY_ALIASES = _MOD.LIMIT_KEY_ALIASES
resolve_limit_key = _MOD.resolve_limit_key
resolve_limit_keys = _MOD.resolve_limit_keys
flatten_toml_limits = _MOD.flatten_toml_limits
parse_and_validate_limit_amount = _MOD.parse_and_validate_limit_amount
get_financial_limits_paths = _MOD.get_financial_limits_paths
parse_financial_limits = _MOD.parse_financial_limits
read_financial_limits = _MOD.read_financial_limits
format_financial_limits_config = _MOD.format_financial_limits_config
write_financial_limits = _MOD.write_financial_limits
format_limit_display_value = _MOD.format_limit_display_value
format_limits_table = _MOD.format_limits_table
main = _MOD.main


if __name__ == "__main__":
    sys.exit(main())
