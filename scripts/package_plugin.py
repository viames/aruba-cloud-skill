"""Package the canonical root skill as installable Codex plugin and marketplace ZIPs."""

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def archive(path, files):
    """Write deterministic archives and verify their complete contents before release."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, content)
    with zipfile.ZipFile(path) as bundle:
        if set(bundle.namelist()) != set(files) or len(bundle.namelist()) != len(files):
            raise ValueError("Archive inventory mismatch")
        for name, content in files.items():
            if bundle.read(name) != content:
                raise ValueError(f"Archive byte mismatch: {name}")


def package():
    """Copy only tracked skill resources; binaries, credentials and inventories are excluded."""
    manifest = json.loads((ROOT / "packaging/plugin.json").read_text())
    version = manifest["version"]
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    families = {"agents", "scripts", "references", "examples", "assets"}
    skill_files = {}
    for name in filter(None, tracked):
        path = Path(name)
        if name == "scripts/package_plugin.py":
            continue
        if name == "SKILL.md" or path.parts[0] in families or name in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
            skill_files["skills/aruba-cloud/" + path.as_posix()] = (ROOT / path).read_bytes()
    files = dict(skill_files)
    files["plugin.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        files[name] = (ROOT / name).read_bytes()
    files["assets/cloud.svg"] = (ROOT / "packaging/cloud.svg").read_bytes()
    files["assets/changes-preview.png"] = (ROOT / "assets/changes-preview.png").read_bytes()
    required = {"skills/aruba-cloud/SKILL.md", "skills/aruba-cloud/scripts/install_cli.py",
                "skills/aruba-cloud/scripts/inventory.py", "skills/aruba-cloud/scripts/reports.py",
                "skills/aruba-cloud/references/provenance.json", "assets/cloud.svg"}
    if not required.issubset(files):
        raise ValueError("Incomplete runtime resources")
    catalog = {"name": "viames-aruba-cloud", "plugins": [{
        "name": "aruba-cloud", "source": {"source": "local", "path": "./plugins/aruba-cloud"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Coding"}]}
    marketplace = {"plugins/aruba-cloud/" + name: content for name, content in files.items()}
    marketplace[".agents/plugins/marketplace.json"] = (json.dumps(catalog, indent=2) + "\n").encode()
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    plugin = output / f"aruba-cloud-{version}-plugin.zip"
    market = output / f"aruba-cloud-{version}-marketplace.zip"
    archive(plugin, files)
    archive(market, marketplace)
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                        for path in (plugin, market))
    (output / "SHA256SUMS").write_text(checksums)
    print(f"Packaged Aruba Cloud {version}: {len(skill_files)} canonical skill files; no CLI binary or credentials.")
    print(checksums, end="")


if __name__ == "__main__":
    package()
