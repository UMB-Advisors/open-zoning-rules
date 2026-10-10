You are an independent reviewer labelling local zoning use rules from one jurisdiction's own zoning ordinance. Another reader has labelled the same text; you are not shown their answers, and your labels are compared with theirs. Label every cell yourself from the text and any page images below. Do not use anything you remember about this or any other jurisdiction, and do not read files or search the web: if the text below does not say it, it is not evidence.

## Task

For every district in the district list and every use class in the taxonomy, return one cell: the status the code gives that use class in that district, with an exact quote and section from the text below. Return exactly one cell per (district_code, use_class) pair.

## Use classes

{taxonomy}

## Status values

- `permitted`: allowed by right, possibly with objective standards. Common forms: P, permitted, by right, PS, P*.
- `conditional`: allowed only after a discretionary approval. Common forms: C, CU, SE (special exception), SUP, S, use permit, special use.
- `prohibited`: expressly not allowed in the district, including a blank table cell when the table's key says a blank means not permitted.
- `unlisted`: no local use in the code, and no definition, captures the class.

## Rules

{rules}

When a class maps to several local uses with different statuses in one district, the most restrictive status wins (prohibited, then conditional, then permitted) and every mapped local use is listed in `local_uses`. A local use maps to a class only if its wording or its definition covers what the class covers and not what it excludes.

## Evidence

Copy every quoted string exactly, character for character, from the text below. Do not paraphrase, correct spelling, or join text from different places into one quote, except for the table form below.

- Status read from a table: `evidence.kind` is `table`. `row_label` is the local use's row label and `column_header` the district's column header, each copied exactly as it appears in the text. `symbol` is the symbol at their intersection, or "" for a blank. `quote` is `"<row_label> | <column_header> | <symbol>"`.
- Status read from prose: `evidence.kind` is `prose` and `quote` is the sentence that names the use and the district, copied exactly.
- `unlisted`: `evidence.kind` is `absence` and `quote` is the use table's caption or heading copied exactly (or the uses-not-listed clause if the code has one). Every term listed under "Term occurrences" for that class must appear in `absence_hits` with the exact quote where it occurs, its section, and the reason it does not capture the class. If you cannot give such a reason, the class is not unlisted: find the use it names.
- `section` is the section, article or table number exactly as printed in the text (for example "Sec. 4-2" or "Table 3.02.05-1").
- When the mapping depends on a definition, add `definition_evidence` with the definition sentence quoted exactly and its section.
- `source_id` is the id in the page marker of the text you quote.

## Districts

{districts}

## Term occurrences in the full code

Each taxonomy term found anywhere in the code, with the lines it occurs on. Use these for `absence_hits` and to find local uses outside the segments below.

{term_hits}

## Code text

{segments}

## Output

Return one JSON object and nothing else:

```
{"cells": [{"district_code": "...", "use_class": "...", "status": "...", "source_id": "...",
  "local_uses": ["..."],
  "evidence": {"kind": "table", "quote": "...", "section": "...", "row_label": "...", "column_header": "...", "symbol": "..."},
  "definition_evidence": {"quote": "...", "section": "..."},
  "absence_hits": [{"term": "...", "quote": "...", "section": "...", "reason": "..."}],
  "notes": "..."}]}
```

Omit `definition_evidence`, `absence_hits` and `notes` when they do not apply. `local_uses` is empty only for `unlisted`.
