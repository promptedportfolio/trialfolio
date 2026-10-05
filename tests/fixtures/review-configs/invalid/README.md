# Invalid review configurations

Each file breaks exactly one rule of the [review configuration](../../../../docs/contracts.md#review-configuration), or of the rules for [every configuration file](../../../../docs/contracts.md#configuration-files), and is otherwise the [documented example](../../../../docs/contracts.md#review-configuration), which `../example.yaml` copies. `tests/contract/test_review_configuration.py` reads each one, expects `config.invalid`, and expects the message to name the key on the file's `# Key:` line, where `-` means the file as a whole. The message never holds the offending value, given on the file's `# Value:` line, where `-` means there's no value to look for: the key is missing, the value is empty or blank, or the problem is the file as a whole. A value longer than 80 characters is `-` there too: the test also checks that no value of 20 characters or more in the file appears in the message.

- **Origin:** written for Trial Folio's tests. Synthetic: the labels, paths, and text are invented, and no value comes from Portfolio123.
- **Schema version:** review configuration 1.0.0.
- **Redistribution:** synthetic, so it may be committed and shared.
- **Criteria:** R02-AC11 ([0.2.0's test pairing](../../../../docs/releases/0.2.0-review.md#test-pairing)).

A new rule needs a new file, and a row here. The test checks that this table and the directory list the same files.

## Structure

| File | Rule it breaks | Key |
|---|---|---|
| `misspelled-key.yaml` | Unknown keys are rejected | `purpos` |
| `misspelled-result-key.yaml` | Unknown keys in a result are rejected | `results[1].descripton` |
| `misspelled-change-key.yaml` | Unknown keys in an intended change are rejected | `results[1].intended_changes[0].reson` |
| `duplicate-key.yaml` | Duplicate keys are rejected | `results[1].run` |
| `credential-key.yaml` | A credential-like key is rejected, at any depth | `results[1].api_key` |
| `wrong-kind.yaml` | `kind` is `review` | `kind` |
| `unsupported-schema-version.yaml` | `schema_version` is a supported version | `schema_version` |
| `missing-kind.yaml` | `kind` is required | `kind` |
| `missing-schema-version.yaml` | `schema_version` is required | `schema_version` |
| `missing-title.yaml` | `title` is required | `title` |
| `missing-baseline.yaml` | `baseline` is required | `baseline` |
| `missing-results.yaml` | `results` is required | `results` |
| `missing-label.yaml` | Each result's `label` is required | `results[1].label` |
| `missing-run.yaml` | Each result's `run` is required | `results[1].run` |
| `missing-setting.yaml` | Each intended change's `setting` is required | `results[1].intended_changes[0].setting` |
| `missing-reason.yaml` | Each intended change's `reason` is required | `results[1].intended_changes[0].reason` |
| `null-value.yaml` | A key has a value; null is rejected | `results[1].description` |
| `anchor-alias.yaml` | Anchors and aliases are rejected | `baseline` |
| `explicit-tag.yaml` | Explicit YAML tags are rejected | `results[1].label` |
| `non-text-key.yaml` | Keys are text | `results[1]` |
| `two-documents.yaml` | A file holds one YAML document | - |
| `not-a-mapping.yaml` | A file is a mapping of keys to values | - |

## Results

| File | Rule it breaks | Key |
|---|---|---|
| `one-result.yaml` | `results` has at least two entries | `results` |
| `baseline-not-a-label.yaml` | `baseline` is the label of one of the results | `baseline` |
| `duplicate-label.yaml` | Each result's label is unique | `results[1].label` |
| `intended-change-on-baseline.yaml` | The baseline declares no intended change | `results[0].intended_changes` |
| `empty-intended-changes.yaml` | `intended_changes`, when given, holds at least one entry; a result that declares nothing leaves it out | `results[1].intended_changes` |

## Settings

| File | Rule it breaks | Key |
|---|---|---|
| `unknown-setting.yaml` | `setting` is one of the 12 declarable settings | `results[1].intended_changes[0].setting` |
| `undeclarable-setting.yaml` | A setting that isn't declarable is rejected | `results[1].intended_changes[0].setting` |
| `setting-listed-twice.yaml` | A result declares each setting at most once | `results[1].intended_changes` |

## Labels

| File | Rule it breaks | Key |
|---|---|---|
| `label-uppercase.yaml` | A label matches `[a-z0-9][a-z0-9_-]{0,63}`: lowercase only | `results[0].label` |
| `label-leading-hyphen.yaml` | A label starts with a letter or a digit | `results[0].label` |
| `label-too-long.yaml` | A label has at most 64 characters (this one has 65) | `results[0].label` |
| `label-with-dot.yaml` | A label holds only letters, digits, `_`, and `-` | `results[0].label` |
| `label-device-name.yaml` | A label isn't a name Windows reserves for a device (`nul`; the contract test checks the other 21) | `results[0].label` |

## Text

| File | Rule it breaks | Key |
|---|---|---|
| `empty-title.yaml` | `title` has 1 to 200 characters | `title` |
| `title-too-long.yaml` | `title` has at most 200 characters (this one has 201) | `title` |
| `purpose-too-long.yaml` | `purpose` has at most 2,000 characters (this one has 2,001) | `purpose` |
| `blank-purpose.yaml` | `purpose`, when given, isn't all whitespace | `purpose` |
| `blank-description.yaml` | `description`, when given, isn't all whitespace | `results[1].description` |
| `description-too-long.yaml` | `description` has at most 500 characters (this one has 501) | `results[1].description` |
| `empty-reason.yaml` | `reason` has 1 to 500 characters | `results[1].intended_changes[0].reason` |
| `blank-reason.yaml` | `reason` isn't all whitespace | `results[1].intended_changes[0].reason` |
| `reason-too-long.yaml` | `reason` has at most 500 characters (this one has 501) | `results[1].intended_changes[0].reason` |
| `empty-run.yaml` | `run` is a non-empty path | `results[1].run` |

## Coerced values

| File | Rule it breaks | Key |
|---|---|---|
| `label-number.yaml` | A label is text, never a number read as one | `results[0].label` |
| `baseline-number.yaml` | `baseline` is text, never a number read as one | `baseline` |
| `setting-number.yaml` | `setting` is text, never a number read as one | `results[1].intended_changes[0].setting` |
