# Invalid ranking snapshot configurations

Each file breaks exactly one rule of the [ranking snapshot configuration](../../../../docs/contracts.md#ranking-snapshot-configuration), or of the rules for [every configuration file](../../../../docs/contracts.md#configuration-files), and is otherwise the [snapshot example](../../../../docs/contracts.md#ranking-snapshot-configuration), which `../example.yaml` copies. Release 0.4.0's [test pairing](../../../../docs/releases/0.4.0-ranking-weights.md#invalid-ranking-cases) lists them. `tests/contract/test_ranking_snapshot_configuration.py` reads each one, expects `config.invalid`, and expects the message to name the key on the file's `# Key:` line, where `-` means the file as a whole, and never to hold the value on its `# Value:` line, where `-` means there's no value to look for, as a whole, not inside a longer name, nor, since TS-T06, any value of 20 characters or more in the file.

- **Origin:** written for Trial Folio's tests by R04-T05, each from the snapshot example. Synthetic: the system names are invented, and no value comes from Portfolio123 or from the owner's account.
- **Schema version:** ranking snapshot configuration 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.
- **Criteria:** the snapshot configuration's rules, in release 0.4.0's [test pairing](../../../../docs/releases/0.4.0-ranking-weights.md#invalid-ranking-cases). Its other checks also run `misspelled-key.yaml` and `unquoted-system.yaml` through the CLI, in `tests/interface/test_run_validation.py`, once `run` reads a snapshot configuration.

A new rule needs a new file, and a row here. The test checks that these tables and the directory list the same files.

## Structure

| File | Rule it breaks | Key |
|---|---|---|
| `misspelled-key.yaml` | Unknown keys are rejected | `sytem` |
| `id-key.yaml` | The system is named by its name: an ID isn't offered | `id` |
| `title-key.yaml` | The file has no title: the configuration that uses the snapshot declares the research | `title` |
| `credential-key.yaml` | A credential-like key is rejected | `api_key` |
| `wrong-kind.yaml` | `kind` is `ranking-snapshot` | `kind` |
| `unsupported-schema-version.yaml` | `schema_version` is a supported version | `schema_version` |
| `missing-kind.yaml` | `kind` is required | `kind` |
| `missing-schema-version.yaml` | `schema_version` is required | `schema_version` |
| `missing-system.yaml` | `system` is required | `system` |
| `null-value.yaml` | A key has a value; null is rejected | `system` |
| `anchor-alias.yaml` | Anchors and aliases are rejected | `system` |
| `explicit-tag.yaml` | Explicit YAML tags are rejected | `system` |
| `duplicate-key.yaml` | Duplicate keys are rejected | `system` |
| `two-documents.yaml` | A file holds one YAML document | - |
| `not-a-mapping.yaml` | A file is a mapping of keys to values | - |

## The system's name

| File | Rule it breaks | Key |
|---|---|---|
| `empty-system.yaml` | `system` is non-empty | `system` |
| `unquoted-system.yaml` | `system`, the name Portfolio123 receives, is written in quotes or as a block scalar (R01-T18) | `system` |
| `system-number.yaml` | `system` is text, never a number | `system` |
