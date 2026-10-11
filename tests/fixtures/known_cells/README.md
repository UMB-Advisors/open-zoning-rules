# Known-answer cell fixtures

Excerpts of primary-source text and the real extractor cells behind four known-answer misses (Z0 report v0.1.0), used by `tests/test_z08_gates.py`. The full texts live only in the uncommitted cache.

| File | Source | Lines |
|---|---|---|
| `us-13097-udc.excerpt.txt` | `us-13097-udc` (bytes sha256 `36d41e6407d3e61b6c7537e1f4110e24d4d867fb5e9db12f5af34f9e24838569`), text from `ozr segment` with spanned table cells kept | raw layer lines 3265-3274 (Table 2.2 key); reconstructed table layer lines 919-932 (page 101 key rows, header, 518210 rows) |
| `us-51143-zo-ch35.excerpt.txt` | `us-51143-zo-ch35` (bytes sha256 `3d6e44bfc8eb8112b8b7fdc62ff97d7174de7b34b0dc4db276f8130e8d96ebab`) | raw lines 129, 2559-2585, 4614, 4660, 4923, 5051-5070, 5444, 5474-5483, joined in order |
| `cells.json` | `jurisdictions/<jid>/cells.extracted.json` as committed on `feat/z0.7-release-v0.1.0` | the extractor cells us-13097 OI and C-H, us-51143 M-2 (`datacenter`) |
