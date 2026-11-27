import io
import unittest
from pathlib import Path
from unittest import mock

from rich.console import Console


class BannerTests(unittest.TestCase):
    def _render(self, width=110, accent="cyan", model="gpt-4o", session_id="abc123"):
        import onno_x.ui as ui

        recorder = Console(width=width, record=True, color_system="truecolor", file=io.StringIO())
        with mock.patch.object(ui, "console", recorder):
            lines = ui.print_banner(model, accent, session_id=session_id)
        return lines, recorder.export_text(styles=False)

    def test_wide_banner_shows_art_tagline_and_status(self):
        lines, out = self._render()
        self.assertGreaterEqual(lines, 10)
        self.assertIn("multi-model coding agent", out)
        self.assertIn("gpt-4o", out)
        self.assertIn("abc123", out)
        self.assertIn("M\"\"MMMM\"\"M", out)
        self.assertIn("/help", out)

    def test_narrow_banner_falls_back_to_wordmark(self):
        lines, out = self._render(width=64)
        self.assertIn("ONNO-X", out)
        self.assertNotIn("M\"\"MMMM\"\"M", out)
        self.assertLess(lines, 10)

    def test_unknown_accent_does_not_crash(self):
        lines, out = self._render(accent="chartreuse")
        self.assertIn("gpt-4o", out)
        self.assertGreater(lines, 0)

    def test_cwd_is_abbreviated_to_home(self):
        import onno_x.ui as ui

        recorder = Console(width=110, record=True, file=io.StringIO())
        with mock.patch.object(ui, "console", recorder):
            ui.print_banner("m", cwd=str(Path.home() / "project"))
        self.assertIn("~/project", recorder.export_text(styles=False))

    def test_pad_to_bottom_uses_given_line_count(self):
        import onno_x.ui as ui

        with mock.patch.object(ui.shutil, "get_terminal_size", return_value=mock.Mock(lines=40)):
            with mock.patch("builtins.print") as printed:
                ui.pad_to_bottom(banner_lines=13, input_box_lines=4)
        padding = printed.call_args[0][0]
        self.assertEqual(padding.count("\n"), 40 - 17)


if __name__ == "__main__":
    unittest.main()
