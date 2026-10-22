#!/usr/bin/env python3
"""Validate public configs and retained pins, then package one Pages snapshot.

The Rust verifier owns document semantics. This tool checks immutable bytes
against their content-addressed paths and published history. It copies only
validated public files, adds checksums, and records their source revision.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ENVIRONMENTS = {"prod": "mainnet", "stage": "testnet"}
STATIC_FILE = "static-wallet-pir-config.json"
DYNAMIC_FILE = "dynamic-wallet-pir-config.json"
PIN_PATTERN = re.compile(r"pins/(prod|stage)/([0-9a-f]{64})/static-wallet-pir-config\.json")
SITE_URL = "https://valargroup.github.io/wallet-pir-config"


class PublicationError(ValueError):
    """A document or output cannot be published without losing an invariant."""


class RustConfigVerifier:
    """Validate a file pair through the authoritative Rust config profile."""

    def __init__(self, executable):
        self.executable = str(executable)

    def verify(self, static_path, dynamic_path, network):
        subprocess.run(
            [self.executable, "verify", "--static-config", str(static_path),
             "--dynamic-config", str(dynamic_path), "--network", network],
            check=True,
            timeout=30,
        )


def git_output(repository, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments], timeout=30
    ).decode().strip()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_file(repository, relative):
    """Refuse symlinked inputs before treating a file as public config."""
    relative = Path(relative)
    path = repository / relative
    if any((repository / parent).is_symlink() for parent in (relative, *relative.parents)):
        raise PublicationError(f"public config must not be a symlink: {relative}")
    if not path.is_file():
        raise PublicationError(f"required public config is missing: {relative}")
    return path


def published_pins(repository, published_ref):
    """Return all pins ever added to the published branch, even if removed later."""
    paths = git_output(
        repository, "log", "--format=", "--name-only", "--diff-filter=A",
        published_ref, "--", "pins/",
    )
    return {line for line in paths.splitlines() if PIN_PATTERN.fullmatch(line)}


def validate_repository(repository, verifier, published_ref="origin/main"):
    """Return the serving allowlist only after every document and pin passes."""
    public_paths = []
    for environment, network in ENVIRONMENTS.items():
        static_relative = f"{environment}/{STATIC_FILE}"
        dynamic_relative = f"{environment}/{DYNAMIC_FILE}"
        static_path = public_file(repository, static_relative)
        dynamic_path = public_file(repository, dynamic_relative)
        verifier.verify(static_path, dynamic_path, network)
        static_pin = f"pins/{environment}/{file_digest(static_path)}/{STATIC_FILE}"
        if public_file(repository, static_pin).read_bytes() != static_path.read_bytes():
            raise PublicationError(f"current static config differs from its pin: {static_pin}")
        public_paths.extend([static_relative, dynamic_relative])

    retained_pins = {
        path.relative_to(repository).as_posix()
        for path in (repository / "pins").rglob(STATIC_FILE)
    }
    for relative in sorted(retained_pins | published_pins(repository, published_ref)):
        match = PIN_PATTERN.fullmatch(relative)
        if not match:
            raise PublicationError(f"invalid immutable pin path: {relative}")
        environment, expected_digest = match.groups()
        pin_path = public_file(repository, relative)
        if file_digest(pin_path) != expected_digest:
            raise PublicationError(f"immutable pin bytes changed: {relative}")
        verifier.verify(
            pin_path, repository / environment / DYNAMIC_FILE, ENVIRONMENTS[environment]
        )
        public_paths.append(relative)
    return sorted(set(public_paths))


def build_snapshot(repository, verifier, output, published_ref="origin/main"):
    """Create a new snapshot atomically; never replace an existing directory."""
    if output.exists() or output.is_symlink():
        raise PublicationError(f"output already exists; choose a new directory: {output}")
    if git_output(repository, "status", "--porcelain", "--untracked-files=normal"):
        raise PublicationError("commit configuration changes before building a serving snapshot")
    revision = git_output(repository, "rev-parse", "HEAD")
    public_paths = validate_repository(repository, verifier, published_ref)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".config-site-", dir=output.parent) as temporary:
        snapshot = Path(temporary) / "snapshot"
        snapshot.mkdir()
        manifest = {"source_revision": revision, "files": {}}
        for relative in public_paths:
            source = public_file(repository, relative)
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            digest = file_digest(destination)
            destination.with_name(destination.name + ".sha256").write_text(digest + "\n")
            manifest["files"][relative] = digest
        (snapshot / ".nojekyll").touch()
        (snapshot / "deployment-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if git_output(repository, "rev-parse", "HEAD") != revision:
            raise PublicationError("source revision changed during snapshot construction")
        if git_output(repository, "status", "--porcelain", "--untracked-files=normal"):
            raise PublicationError("source files changed during snapshot construction")
        snapshot.rename(output)
    return manifest


def print_pins(repository):
    for environment in ENVIRONMENTS:
        digest = file_digest(repository / environment / STATIC_FILE)
        print(f"{environment}: {SITE_URL}/pins/{environment}/{digest}/{STATIC_FILE}"
              f"?checksum=sha256:{digest}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "build"))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--validator", default="wallet-pir-config")
    parser.add_argument("--published-ref", default="origin/main")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    repository = arguments.repository.resolve()
    verifier = RustConfigVerifier(arguments.validator)
    try:
        if arguments.command == "verify":
            validate_repository(repository, verifier, arguments.published_ref)
        else:
            if arguments.output is None:
                parser.error("build requires --output")
            build_snapshot(repository, verifier, arguments.output.absolute(), arguments.published_ref)
        print_pins(repository)
    except (PublicationError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"config publication failed: {error}\n")


if __name__ == "__main__":
    main()
