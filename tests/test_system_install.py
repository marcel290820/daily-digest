import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class InstallTimers(unittest.TestCase):
    def test_new_timer_activates_and_operator_disabled_timer_stays_disabled(
        self,
    ) -> None:
        script = (Path(__file__).parents[1] / "deploy/install.sh").read_text()
        # Exercise installation ordering without root privileges or host mutations.
        script = script.replace("if [[ $EUID -ne 0 ]]; then", "if false; then", 1)
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "mocks.sh"
            env_file.write_text(r"""installed_system=0
install() { if [[ "$*" == *daily-digest-system.timer* ]]; then installed_system=1; fi; }
systemctl() {
  if [[ "$1" == is-enabled ]]; then
    case "$2" in
      daily-digest-news.timer) echo disabled;;
      daily-digest-system.timer) if [[ "$installed_system" == 1 ]]; then echo disabled; else echo not-found; return 1; fi;;
      *) echo enabled;;
    esac
  else printf "%s\n" "$*"; fi
}
""")
            installer = Path(tmp) / "install.sh"
            installer.write_text(script)
            result = subprocess.run(
                ["bash", str(installer)],
                env={**os.environ, "BASH_ENV": str(env_file)},
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertIn("enable --now daily-digest-system.timer", result.stdout)
        self.assertIn("skipping daily-digest-news.timer", result.stdout)
        self.assertNotIn("enable --now daily-digest-news.timer", result.stdout)
