# Invalid ranking definitions

Each file is [`../value-momentum.xml`](../README.md), the [ranking example](../../../../../docs/contracts.md#ranking-example)'s definition, broken one way: it breaks exactly one rule of a [ranking definition](../../../../../docs/contracts.md#ranking-definitions)'s text or form. A definition can't hold a comment, so this table maps each file to its rule, and to the line its message names: the line of the element at fault, or of the text, the byte, or the declaration at fault. Release 0.4.0's [invalid ranking cases](../../../../../docs/releases/0.4.0-ranking-weights.md#invalid-ranking-cases) list them.

`tests/contract/test_ranking_definitions.py` reads each one through [`../../../screen-configs/definition.yaml`](../../../screen-configs/README.md) and through [`../../ranking-example.yaml`](../../README.md)'s baseline, each copied with the file in place of `value-momentum.xml`. Each fails with `config.invalid`, and the message names the configuration's key, `ranking.definition` or `baseline.ranking.definition`, the rule, and the line below, and holds no text of the definition. The test checks that this table and the directory list the same files.

- **Origin:** written for Trial Folio's tests by R04-T06, each from `value-momentum.xml`. Synthetic: no definition, name, or weight comes from Portfolio123 or from the owner's account.
- **Schema version:** the ranking definition's form, which release 0.4.0's R04-T02 specified.
- **Redistribution:** synthetic, so they may be committed and shared.
- **Criteria:** R04-AC02, in `tests/contract/test_ranking_definitions.py`. The test pairing also runs `not-well-formed.xml` and `weight-zero.xml` through `definition.yaml`, through the CLI, in `tests/interface/test_run_validation.py`, once `run` reads a definition (R04-T12).

| File | Rule it breaks | Line |
|---|---|---|
| `not-well-formed.xml` | The definition is well-formed XML 1.0: line 5's end tag is `</StockFormul>` | 5 |
| `not-utf-8.xml` | The file is UTF-8 text: line 4's formula is a Latin-1 byte, `0xE9`, in place of the ellipsis | 4 |
| `byte-order-mark.xml` | The file has no byte-order mark | 1 |
| `root-not-ranking-system.xml` | The root element is `RankingSystem`: here it's `Ranking` | 1 |
| `text-after-root.xml` | Only white space follows the `RankingSystem` element: line 27 holds a sentence | 27 |
| `xml-declaration.xml` | The definition holds no XML declaration: line 1 is one | 1 |
| `doctype.xml` | The definition holds no document type declaration: line 1 is one | 1 |
| `comment.xml` | The definition holds no comment: line 11 is one, in the Momentum composite | 11 |
| `processing-instruction.xml` | The definition holds no processing instruction: line 18 is one, before the Quality composite | 18 |
| `no-node.xml` | `RankingSystem` holds at least one node | 1 |
| `empty-composite.xml` | A `Composite` holds at least one node: line 18's Quality composite holds none | 18 |
| `conditional-node.xml` | A node is a `Composite`, a `StockFormula`, or a `StockFactor`: line 18's Quality is a `Conditional` | 18 |
| `ind-formula-node.xml` | A node is one of the three types: line 14's Year Return is an `IndFormula` | 14 |
| `text-between-nodes.xml` | A ranking system, or a composite, holds only white space between its nodes: line 10 holds a sentence | 10 |
| `stock-formula-other-element.xml` | A `StockFormula` holds no element but `Formula`: line 5 is a `Description` element in Earnings Yield | 5 |
| `stock-factor-other-element.xml` | A `StockFactor` holds no element but `Factor`: Gross Margin is a `StockFactor`, without a name, whose line 23 holds a `Formula` | 23 |
| `formula-holds-element.xml` | A `Formula` holds no element: line 4's holds a `Note` | 4 |
| `missing-weight.xml` | Every node has a `Weight`: line 6's Sales Yield has none | 6 |
| `weight-zero.xml` | A weight is greater than 0: line 10's Momentum is `0` | 10 |
| `weight-percent.xml` | A weight has no percent sign: line 2's Value is `40%` | 2 |
| `weight-space.xml` | A weight has no white space: line 11's Six-Month Return is `50 ` | 11 |
| `weight-sign.xml` | A weight has no sign: line 18's Quality is `+30` | 18 |
| `weight-exponent.xml` | A weight has no exponent: line 14's Year Return is `5e1` | 14 |
| `weight-five-decimals.xml` | A weight has at most 4 digits after the decimal point: line 19's Return on Equity is `50.00001` | 19 |
| `weight-too-large.xml` | A weight is less than 10^16: line 22's Gross Margin is `10000000000000000` | 22 |
| `weight-character-reference.xml` | A weight is written as the decimal itself, without a character reference: line 3's Earnings Yield is `&#53;0` | 3 |
