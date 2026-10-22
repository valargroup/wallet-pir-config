"""Publication invariants independent of the Rust document schema tests."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "config_site", PROJECT_ROOT / "scripts" / "config_site.py"
)
config_site = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(config_site)


class RecordingVerifier:
    def __init__(self):
        self.checked_pairs = []

    def verify(self, static_path, dynamic_path, network):
        self.checked_pairs.append((static_path, dynamic_path, network))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name)
        self.verifier = RecordingVerifier()
        self.git("init", "-b", "main")
        (self.repository / ".gitignore").write_text("/_site/\n/.config-site-*/\n")
        for environment in config_site.ENVIRONMENTS:
            for filename in (config_site.STATIC_FILE, config_site.DYNAMIC_FILE):
                destination = self.repository / environment / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((PROJECT_ROOT / environment / filename).read_bytes())
            static_path = self.repository / environment / config_site.STATIC_FILE
            digest = config_site.file_digest(static_path)
            pin_path = self.repository / "pins" / environment / digest / config_site.STATIC_FILE
            pin_path.parent.mkdir(parents=True)
            pin_path.write_bytes(static_path.read_bytes())
        self.git("add", ".gitignore", "prod", "pins")
        self.git("-c", "user.name=Publication tests", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "Initial configuration fixture")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.repository), *arguments], stderr=subprocess.STDOUT,
            timeout=15,
        ).decode().strip()

    def production_pin(self):
        return next((self.repository / "pins" / "prod").rglob(config_site.STATIC_FILE))

    def test_published_pin_cannot_be_deleted_after_current_alias_changes(self):
        old_pin = self.production_pin()
        static_path = self.repository / "prod" / config_site.STATIC_FILE
        static_path.write_bytes(static_path.read_bytes() + b"\n")
        new_pin = old_pin.parent.parent / config_site.file_digest(static_path) / static_path.name
        new_pin.parent.mkdir()
        new_pin.write_bytes(static_path.read_bytes())
        old_pin.unlink()
        with self.assertRaisesRegex(config_site.PublicationError, "required public config is missing"):
            config_site.validate_repository(self.repository, self.verifier)

    def test_changed_pin_bytes_are_rejected(self):
        pin = self.production_pin()
        pin.write_bytes(pin.read_bytes() + b"\n")
        with self.assertRaises(config_site.PublicationError):
            config_site.validate_repository(self.repository, self.verifier)

    def test_symlinked_config_is_rejected(self):
        dynamic_path = self.repository / "prod" / config_site.DYNAMIC_FILE
        dynamic_path.unlink()
        target = self.repository / "outside-public.json"
        target.write_text("{}\n")
        dynamic_path.symlink_to(target)
        with self.assertRaisesRegex(config_site.PublicationError, "must not be a symlink"):
            config_site.validate_repository(self.repository, self.verifier)

    def test_snapshot_copies_only_public_files_and_checks_every_pin(self):
        (self.repository / "private-local.txt").write_text("not a public document\n")
        self.git("add", "private-local.txt")
        self.git("-c", "user.name=Publication tests", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "Add a nonpublic fixture file")
        snapshot = self.repository / "_site"
        manifest = config_site.build_snapshot(self.repository, self.verifier, snapshot)
        self.assertFalse((snapshot / "private-local.txt").exists())
        self.assertFalse((snapshot / ".git").exists())
        self.assertEqual(len(self.verifier.checked_pairs), 2)
        self.assertEqual(manifest["source_revision"], self.git("rev-parse", "HEAD"))
        self.assertEqual(len(manifest["files"]), 3)
        self.assertFalse((snapshot / "stage").exists())
        self.assertFalse((snapshot / "pins" / "stage").exists())
        for relative, digest in manifest["files"].items():
            self.assertEqual(config_site.file_digest(snapshot / relative), digest)
            self.assertEqual((snapshot / (relative + ".sha256")).read_text(), digest + "\n")

    def test_existing_output_is_preserved(self):
        output = self.repository / "_site"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("preserve me")
        with self.assertRaisesRegex(config_site.PublicationError, "output already exists"):
            config_site.build_snapshot(self.repository, self.verifier, output)
        self.assertEqual(sentinel.read_text(), "preserve me")

    def test_uncommitted_sources_cannot_be_published(self):
        (self.repository / "prod" / config_site.DYNAMIC_FILE).write_text("{}\n")
        output = self.repository / "_site"
        with self.assertRaisesRegex(config_site.PublicationError, "commit configuration changes"):
            config_site.build_snapshot(self.repository, self.verifier, output)
        self.assertFalse(output.exists())

    def test_pin_summary_matches_the_immutable_file_and_is_copyable(self):
        digest = config_site.file_digest(self.production_pin())
        expected = (
            f"{config_site.SITE_URL}/pins/prod/{digest}/{config_site.STATIC_FILE}"
            f"?checksum=sha256:{digest}"
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            config_site.print_pin_summary(self.repository)
        summary = output.getvalue()
        self.assertIn(f"| Production | `{expected}` |", summary)
        self.assertIn(f"```text\nproduction={expected}\n```", summary)
        self.assertNotIn("stage", summary)

    def test_pin_summary_refuses_changed_immutable_bytes(self):
        self.production_pin().write_text("{}\n")
        with self.assertRaisesRegex(config_site.PublicationError, "immutable pin bytes differ"):
            config_site.static_pin_urls(self.repository)


if __name__ == "__main__":
    unittest.main()
