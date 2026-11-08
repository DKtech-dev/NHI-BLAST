# Diff fixtures

Saved `nhi-blast-report/1.1` documents used by `tests/test_diff_cli.py`. They are generated, not
hand-written: `base.json` is a `repo-write` scan of `fx07-incident`; `head-pinned.json` is the same scan after
pinning the mutable `tj-actions/changed-files@v45` reference in `release.yml` to a commit SHA;
`base-without-oidc.json` is `base.json` with the `NHB-OIDC-002` finding removed in memory so the unchanged
document diffs as a report with one new finding. They contain no credential values.
