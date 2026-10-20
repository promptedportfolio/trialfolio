# Ranking definitions

A ranking system's definition is the XML that Portfolio123's website shows in the ranking system's Text Editor, under Ranking System → Factors. From release 0.4.0, a [screen configuration](screen-configuration.md#ranking)'s `ranking`, or an [experiment's](experiment-configuration.md) baseline's, can give one in a file beside the configuration, or by a [ranking snapshot](../how-to/take-a-ranking-snapshot.md), and an experiment's [ranking variants](experiment-configuration.md#ranking-variants) change its weights by node paths. This page gives the rules a definition and a node path follow.

[Ranking definitions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-definitions) and [node paths](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#node-paths), in the specification, give every rule. Portfolio123 documents no schema for the XML, so Trial Folio accepts the form that live calls read and sent, and nothing else until a live call verifies it.

## An example

This is the definition of the [ranking example](experiment-configuration.md#a-ranking-example), in a file `ranking/value-momentum.xml` beside the configuration: three composites, Value, Momentum, and Quality, of two factors each. Its names and weights are invented, and its formulas are left out, as `…`. A definition you copy from the website has your system's names, weights, and formulas.

```xml
<RankingSystem RankType="Higher">
	<Composite Name="Value" Weight="40" RankType="Summation">
		<StockFormula Name="Earnings Yield" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
		<StockFormula Name="Sales Yield" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
	</Composite>
	<Composite Name="Momentum" Weight="30" RankType="Summation">
		<StockFormula Name="Six-Month Return" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
		<StockFormula Name="Year Return" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
	</Composite>
	<Composite Name="Quality" Weight="30" RankType="Summation">
		<StockFormula Name="Return on Equity" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
		<StockFormula Name="Gross Margin" Weight="50" RankType="Higher" Scope="Universe" Description="">
			<Formula>…</Formula>
		</StockFormula>
	</Composite>
</RankingSystem>
```

## The file

- **Where it is.** The configuration's `definition` is the file's path, read from the configuration file's folder, as every path in a configuration is.
- **Its text.** The file is UTF-8 text, without a byte-order mark. Save it as UTF-8: a byte-order mark, or a file saved as UTF-16, fails. Windows line endings are read as line feeds, so the definition sent never holds a carriage return, and a copy checked out with either kind of line ending gives the same definition, and the same case.
- **Read once.** Trial Folio reads the file when it validates the configuration, before it shows the plan, and copies it, byte for byte, beside each plan's `configuration.yaml`, as `definition.xml`. So the copy is the definition you approved, even if the file changes while the plan waits for your approval.
- **A changed file changes the plan.** Each command reads the file again. So a changed definition gives a new plan to approve: in an experiment, a [revision](../how-to/revise-an-experiment.md), as a changed setting does.

## Its form

- **One `RankingSystem` element,** with only white space before or after it. An XML declaration, a document type declaration, a comment, or a processing instruction, anywhere, fails. A formula may use XML's references, such as `&lt;` for `<`.
- **Three kinds of node:**
    - **`Composite`,** which holds at least one node of its own;
    - **`StockFormula`,** a factor with a formula, in its `Formula` element;
    - **`StockFactor`,** a factor chosen from Portfolio123's list, named in its `Factor` element.
- **No other node.** Any other element where a node goes, such as a conditional node, fails, until a live call verifies it. Between nodes there's only white space.
- **A weight on every node.** Each node's `Weight` is a number greater than 0, written in plain notation, with at most 4 digits after the decimal point, such as `50` or `12.5`: no percent sign, sign, exponent, or space. A weight of 0, which Portfolio123 reads as equal weighting, fails. Siblings' weights needn't sum to 100.
- **Names.** A node's name is its `Name` attribute. A node without one, such as a `StockFactor` usually is, has no name. Two nodes may share a name; a [node path](#node-paths) then names each by its position.
- **What Trial Folio doesn't read.** Every other attribute, such as `RankType` and `Scope`, and each formula's text, is sent as the file writes it. Trial Folio doesn't read a formula, as it doesn't read a screen's rules.

## The ranking method, currency, and type

- **`ranking_method`** is required beside `definition`: `percentile_nas_negative`, sent as 2, or `percentile_nas_neutral`, sent as 4, Percentile NAs Negative and Percentile NAs Neutral, the two methods Portfolio123 documents for writing a ranking system. A snapshot gives its system's, which must be one of the two.
- **The currency and the type are fixed:** each case writes its definition with the currency USD and the type stock, as every backtest Trial Folio sends uses them. So a snapshot of a system in another currency, or of an ETF ranking system, can't be a ranking.

## Node paths

A ranking variant names a node by its path: the nodes from the top level down to it, each given by a segment, separated by `/`. In the [example](#an-example), `Value` is the top-level composite named Value, and `Value/Sales Yield` the factor named Sales Yield in it.

- **A name,** character for character, with the same case and spaces as the definition's `Name`.
- **A position,** `#` and a whole number, such as `#2`, names its parent's node at that position, counting from 1, in the definition's order, whether or not it has a name. So `Value/#2` is Sales Yield too. A position names a node without a name, such as a `StockFactor`, and one of two nodes that share a name. A segment that starts with `#` is always a position, so `#01` or `#a` fails; a name that starts with `#` is written `\#`.
- **Escapes.** In a segment, `\/` stands for a `/`, `\\` for a `\`, and `\#`, at its start, for a `#`. So a composite named `P/E` is written `P\/E`. Inside single quotes, YAML keeps a path's `\` as it is, so `'Value/P\/E'` works as written. Inside double quotes, YAML reads its own escapes first, so each `\` is written `\\`: `"Value/P\\/E"` is the same path.
- **In quotes.** Write each path in single quotes, as a `set`'s key and as a `remove`, since a name can hold a space followed by `#`, which YAML would read as the start of a comment. A path without quotes fails with `config.invalid`.
- **One node.** A path whose segment names no node, or more than one, fails with `config.invalid`, as does an empty segment, or a position of 0 or past its parent's last node.
- **A credential-like word.** A `set`'s paths are keys, so a path that holds a word such as `secret` or `token` fails, as any configuration's key does. Name such a node by its position instead.

**Canonical paths.** Wherever Trial Folio names a node itself, in a plan, `settings.csv`, `differences.csv`, or a report, it writes the node's canonical path: each segment is the node's name, with the escapes above, when no other node of its parent has that name, and its position otherwise. So however a configuration names a node, Trial Folio names it one way: a top-level `StockFactor` without a name, the third node, is `#3`.

## A case's identity

A case's `ranking` setting holds its definition's hash, `sha256:` and 64 hex digits, and its ranking method, and a weight row for each node follows it. So the `case_id` covers the definition, byte for byte, its ranking method, and its weights. Where it came from doesn't count: the same definition, given in a file or read by a snapshot, with the same ranking method and the other settings the same, gives the same case. The plan records the source, so the plan hash covers it. A snapshot's ranking method is its system's, so a snapshot of the same bytes, whose system has another ranking method than the file's configuration gives, is another case ([plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition)).

## What's rejected

Each of these fails with `config.invalid`, exit code 3, before anything is sent or created:

- a file that isn't UTF-8 text, or that holds a byte-order mark or a NUL character;
- XML that isn't well-formed, a root element other than `RankingSystem`, or a declaration, a comment, or a processing instruction;
- a node of another kind, or another element in a factor than its `Formula` or `Factor`;
- a node without a `Weight`, a weight of 0, or one written with a percent sign, a sign, an exponent, more than 4 digits after the decimal point, or a reference such as `&#48;`;
- a composite without a node, or text between nodes;
- something other than a file at the path.

The message names the configuration's key, such as `ranking.definition` or `baseline.ranking.definition`, the rule, and the line of the element at fault. It never quotes the definition, which is your strategy's definition, so it's safe to log. A path where nothing exists, or a file that can't be read, fails with `input.not_found`, exit code 3, with the reason.
