# Aruba Cloud skill for Codex

Manage Aruba Cloud CMP resources through Aruba's official [`acloud` CLI](https://github.com/Arubacloud/acloud-cli), built on the official [Go SDK](https://github.com/Arubacloud/sdk-go).

This community skill adds reusable operating instructions and a read-only inventory helper. It is independent of Aruba and is not an official Aruba product. It does not require Go or third-party Python packages.

## What it does

- Inventories projects, cloud servers, block storage, VPCs, Elastic IPs, DBaaS, Kubernetes clusters and container registries.
- Collects multiple pages and detects repeated pages, changing totals and incomplete collections.
- Separates permission/service errors from verified empty results; partial reports exit with status `2`.
- Writes new JSON reports with mode `0600` and refuses to overwrite existing files.
- Guides authorized management operations through the official CLI, with explicit account/project selection and post-operation state checks.
- Includes direct SDK guidance when application code is needed.

Inventory covers the selected resource families, not every Aruba service or billing. A scan is not an atomic snapshot. An empty CMP inventory does not prove that legacy VPS or other Aruba products do not exist.

## Install

Requirements: Python 3.10+, macOS or Linux, arm64 or amd64, and network access to GitHub for the initial CLI download. Initial integration tests were run on macOS arm64; other supported release targets are selected by the installer and covered by the CI matrix where available.

Install into your personal Codex skill directory:

```sh
git clone https://github.com/viames/aruba-cloud-skill.git "$HOME/.codex/skills/aruba-cloud"
python3 "$HOME/.codex/skills/aruba-cloud/scripts/install_cli.py"
python3 "$HOME/.codex/skills/aruba-cloud/scripts/inventory.py" doctor
```

For a custom `CODEX_HOME`, use its `skills/aruba-cloud` directory instead. Do not overwrite an existing installation without reviewing local changes. The skill will be available on your next Codex turn; invoke it with `$aruba-cloud` or ask to manage Aruba Cloud.

The installer downloads **acloud 1.0.0** from the official GitHub release and checks a SHA-256 pinned in `references/provenance.json` before installation. Downloaded binaries and local install receipts stay in ignored `bin/`. No shell profile, global executable path or MCP configuration is changed. A checksum verifies the selected release bytes; it is not an independent publisher signature.

## Connect your account

Create a client credential in [Aruba CMP](https://my.arubacloud.com): **UTILITIES → Developer Tools → Client Credentials → Create Client Credential**. Save the secret when created; [Aruba only displays it during creation](https://kb.arubacloud.com/en/utilities/api/client-credentials/creating.aspx).

In an interactive terminal:

```sh
"$HOME/.codex/skills/aruba-cloud/bin/acloud" config profile set personal --client-id YOUR_CLIENT_ID
```

The CLI prompts for the secret with hidden input. Do not paste secrets into a chat, use a command-line secret flag, or commit credentials. The CLI stores its configuration in `$XDG_CONFIG_HOME/acloud/config.yaml`, defaulting to `~/.config/acloud/config.yaml`, with restricted permissions; it is plaintext, not a secret vault. A secret manager can instead inject `ACLOUD_CLIENT_ID` and `ACLOUD_CLIENT_SECRET` into the process environment.

Environment credentials override file profiles, even with `--profile`. Check for unexpected overrides when switching accounts. The `doctor` command reports variable names and configuration presence only; it neither reveals secrets nor tests authentication.

## Read-only inventory

```sh
python3 "$HOME/.codex/skills/aruba-cloud/scripts/inventory.py" inventory \
  --profile personal \
  --output ./inventory.json
```

Restrict the project or resource families:

```sh
python3 "$HOME/.codex/skills/aruba-cloud/scripts/inventory.py" inventory \
  --profile personal --project-id PROJECT_ID \
  --kinds servers,volumes,vpcs --output ./inventory-project.json
```

Kinds: `servers`, `volumes`, `vpcs`, `ips`, `dbaas`, `kaas`, `registries`.

Check both the exit code and `complete`. A failed family has `count: null` and `items: null`, rather than zero. Error details are reduced to local diagnostic codes to keep response bodies out of reports. Reports contain infrastructure metadata: keep them private.

The inventory helper only lists resources. Installing this skill does not grant permission to create, delete, power on/off or change cloud resources. Management instructions use the authorization in the current user request; they do not require repeated approval for an already authorized operation. Existing per-resource restrictions still apply. Never enable CLI `--debug` with real credentials in shared logs: it may expose authentication headers.

## Test

```sh
python3 scripts/install_cli.py
python3 scripts/test_inventory.py
```

Tests run the actual official CLI against a local HTTP/OAuth fixture with fake credentials. They cover pagination across projects, empty resources across all seven families, permission failures, repeated pages and output overwrite protection. They do not contact Aruba or create cloud resources. A passing local/CI test does not establish authenticated account access or production compatibility.

## Files and maintenance

- [`SKILL.md`](SKILL.md): Codex operating instructions (Italian; examples and tools work independently of language).
- [`references/operations.md`](references/operations.md): credentials, CLI use and scope.
- [`references/sdk.md`](references/sdk.md): direct Go SDK integration.
- [`references/provenance.json`](references/provenance.json): pinned release and platform archive checksums.

Review upstream release notes and CLI/SDK compatibility before updating the pinned version. Re-run the fixture tests after an update. The installer does not silently upgrade the CLI.

## License

Skill instructions and helper code: [MIT](LICENSE), copyright 2026 Viames Marino. Downloaded `acloud` and its SDK dependencies remain under their respective upstream licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
