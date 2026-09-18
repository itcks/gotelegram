import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "gotelegram-bot" / "bot.py"
CATALOG_PATH = ROOT / "templates_catalog.json"
INSTALL_PATH = ROOT / "install.sh"


class BotFeatureTests(unittest.TestCase):
    def test_catalog_contains_template_ids_that_break_raw_callback_data(self):
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        raw_lengths = [
            len(f"pro_tpl_{tpl['id']}".encode("utf-8"))
            for cat in catalog.get("categories", [])
            for tpl in cat.get("templates", [])
        ]

        self.assertTrue(any(length > 64 for length in raw_lengths))

    def test_bot_uses_short_template_callback_keys(self):
        source = BOT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("callback_data=f\"pro_tpl_{tpl['id']}\"", source)
        self.assertNotIn('callback_data=f"pro_confirm_{tpl_id}"', source)
        self.assertIn("pro_template_map", source)
        self.assertIn("resolve_pro_template_id", source)

    def test_template_callbacks_are_restart_safe_hashes(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        category_body = re.search(
            r"async def cb_pro_category\(.*?(?=\n\n(?:async )?def |\n\n#)",
            source,
            flags=re.S,
        )
        resolve_body = re.search(
            r"def resolve_pro_template_id\(.*?(?=\n\n(?:async )?def |\n\n#)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(category_body)
        self.assertIsNotNone(resolve_body)

        self.assertIn('pro_template_key_for_id(context, tpl["id"])', category_body.group(0))
        self.assertNotIn("enumerate(templates)", category_body.group(0))
        self.assertNotIn("mapping.clear()", category_body.group(0))
        self.assertIn("load_json(TEMPLATES_CATALOG)", resolve_body.group(0))
        self.assertIn("hashlib.sha1", resolve_body.group(0))

    def test_telemt_version_checks_systemd_path_fallbacks(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        version_body = re.search(
            r"async def get_telemt_version\(\).*?(?=\n\n(?:async )?def |\n\n#)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(version_body)
        body = version_body.group(0)

        self.assertIn('"--version"', body)
        self.assertIn('"-V"', body)
        self.assertIn('"/usr/local/bin/telemt"', body)
        self.assertIn("for command in", body)
        self.assertIn("for args in", body)
        self.assertNotIn('"-v"', body)

    def test_telemt_update_menu_reuses_version_helper(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        update_body = re.search(
            r"async def cb_menu_update\(.*?(?=\n\n(?:async )?def |\n\n#)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(update_body)
        body = update_body.group(0)

        self.assertIn("await get_telemt_version()", body)
        self.assertNotIn('sh("telemt", "--version")', body)

    def test_installer_auto_updates_existing_bot_files(self):
        source = INSTALL_PATH.read_text(encoding="utf-8")
        auto_body = re.search(
            r"auto_update_bot_if_possible\(\).*?(?=\n\n[A-Za-z0-9_]+\(\) |\n\n#)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(auto_body)

        auto_text = auto_body.group(0)
        self.assertIn('bot_service_status', auto_text)
        self.assertIn('bot_install', auto_text)
        self.assertIn('cmp -s "$SCRIPT_DIR/gotelegram-bot/bot.py" "$BOT_DIR/bot.py"', auto_text)
        self.assertIn('cmp -s "$SCRIPT_DIR/gotelegram-bot/i18n.py" "$BOT_DIR/i18n.py"', auto_text)
        self.assertIn('cmp -s "$SCRIPT_DIR/gotelegram-bot/requirements.txt" "$BOT_DIR/requirements.txt"', auto_text)
        self.assertIn('auto_migrate_legacy_state || true\n    auto_update_bot_if_possible || true\n    auto_install_admin_web_if_possible || true', source)


if __name__ == "__main__":
    unittest.main()
