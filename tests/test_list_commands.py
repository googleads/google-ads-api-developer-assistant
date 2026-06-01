import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

import list_commands


class TestListCommands(unittest.TestCase):

    def test_load_commands_adds_slash_prefix_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands_dir = pathlib.Path(tmp)
            (commands_dir / "explain.toml").write_text(
                'description = "Explain a Google Ads concept"\n',
                encoding="utf-8",
            )

            commands = list_commands.load_commands(commands_dir)

        self.assertEqual(commands, [("/explain", "Explain a Google Ads concept")])

    def test_load_commands_uses_default_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands_dir = pathlib.Path(tmp)
            (commands_dir / "step_by_step.toml").write_text("", encoding="utf-8")

            commands = list_commands.load_commands(commands_dir)

        self.assertEqual(commands, [("/step_by_step", "No description found")])

    def test_print_commands_aligns_descriptions(self):
        output = io.StringIO()

        with redirect_stdout(output):
            list_commands.print_commands([
                ("/a", "short"),
                ("/longer", "long"),
            ])

        self.assertEqual(output.getvalue(), "/a        short\n/longer   long\n")

    def test_missing_directory_exits(self):
        missing_dir = pathlib.Path("/path/that/does/not/exist")

        with self.assertRaises(SystemExit) as context:
            list_commands.load_commands(missing_dir)

        self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
