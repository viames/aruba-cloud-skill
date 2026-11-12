# Offline reports and inventory comparisons

Use `scripts/reports.py` for deterministic Markdown output from saved inventory JSON. It uses Python 3.10+ and the standard library only. It does not load credentials, execute the CLI, or call cloud APIs.

## Render an inventory

```sh
python3 scripts/reports.py render /private/before.json --output /private/report.md
```

The summary includes account label, collection window, project scope, per-project/family counts, and diagnostic codes. `Unknown` is distinct from a verified zero. Only completed collections contribute to the observed-resource subtotal; an incomplete project listing can leave additional projects unobserved. Report format versions 1 and 2 are accepted for rendering.

## Collect comparable inventories

```sh
python3 scripts/inventory.py inventory --profile personal \
  --account-label my-account --output /private/before.json
# At a later time, with the same account, endpoint configuration, project scope and kinds:
python3 scripts/inventory.py inventory --profile personal \
  --account-label my-account --output /private/after.json
python3 scripts/reports.py diff /private/before.json /private/after.json \
  --output /private/changes.md
```

An account label is a stable, non-secret label supplied by the operator. It is **not an authenticated account identifier**. Establish the intended account in the current task before choosing the label. Profiles may be renamed or repointed, and credentials in the environment override profile credentials. Reusing a label for a different account makes its meaning unreliable.

The inventory now writes schema version 2 with account label, explicit project selection (or all visible projects), and a hash of the `ACLOUD_BASE_URL` / `ACLOUD_TOKEN_ISSUER_URL` environment hints. URLs and credential values are not stored in that scope record. The hash does not inspect saved CLI endpoint configuration or prove the effective endpoint/account. The same account label, compatible configuration, and scope remain the operator's responsibility.

Comparisons require version 2 reports, matching nonempty account labels, endpoint hints, source version, project selection, and selected families. The second collection must start after the first finishes. A version 1 inventory can still be rendered; collect new labeled inventories for comparisons. Do not edit labels or scope metadata to bypass a mismatch.

## Interpret changes

- Resources are matched by project ID, family, and resource ID. Changing list order or object key order does not create changes.
- `Added` and `Removed` mean present in only one completed collection. They describe observed inventory differences, not proof of cloud creation/deletion or who acted.
- `Modified` means stored resource data changed. The report shows JSON Pointer field paths, not raw before/after values. Metadata, status and order-sensitive arrays are included. Up to 20 paths per resource are shown, with an explicit count of additional paths.
- A failed family is uncomparable. Other completed families in the same project can still be compared. Missing projects are reported as visibility changes; their resources are not automatically classified as added or removed.
- An incomplete project listing prevents assertions about project visibility changes. Its resource comparisons remain unverified.
- Unobserved scopes cannot be described as unchanged. Neither scan is atomic, and permissions or visibility may change between scans.

Outputs contain infrastructure identifiers and field names. Keep them private. Markdown summaries deliberately omit raw resource properties. Resource/project text is escaped so names cannot introduce embedded images, HTML, or additional table rows.

## Exit codes and output files

| Result | Exit code | Markdown file |
| --- | --- | --- |
| Complete render or compatible complete comparison | `0` | Written |
| Incomplete inventory or partially comparable inventories | `2` | Written, with unknown/uncomparable scopes |
| Invalid JSON/schema or incompatible scope | `2` | No new report produced |

I/O errors also return `2`. Use a new output path; parent directories must already exist. New Markdown files use mode `0600`, and the writer refuses existing files and symlinks. A success message prints the output path and `complete` status. Check both the exit code and the report.

Common refusal codes:

| Code | Meaning |
| --- | --- |
| `scope_not_recorded` | Collect version 2 inventories with recorded scope |
| `account_label_required` | A snapshot lacks its account label |
| `account_label_mismatch` | The account labels differ |
| `project_scope_mismatch` | Explicit project selection and all-project selection differ |
| `resource_scope_mismatch` | Selected resource families differ |
| `endpoint_hint_mismatch` | Endpoint environment hints differ |
| `inventory_source_mismatch` | Inventory CLI source versions differ |
| `overlapping_or_reversed_collections` | Collection windows overlap or are in reverse order |

## Try the committed examples

All files in `examples/before.json`, `examples/after.json`, `examples/report.md`, and `examples/changes.md` contain synthetic data generated through the real CLI and localhost fixture.

```sh
python3 scripts/reports.py render examples/before.json --output /private/example-report.md
python3 scripts/reports.py diff examples/before.json examples/after.json --output /private/example-changes.md
```

To generate fresh fixture snapshots and reports after installing the pinned CLI:

```sh
python3 scripts/demo.py --output-dir /private/new-demo-directory
```

The demo directory must be new; it is created with mode `0700` and its files with mode `0600`. Without `--output-dir`, temporary demo artifacts are removed on exit. Fixture results do not establish live Aruba access or production compatibility.
