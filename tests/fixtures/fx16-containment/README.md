# fx16-containment

Input for the offline containment what-if (`nhi-blast whatif`). One deploy job holds an
id-token and assumes `ci-deploy` (session TTL 3600 s). The role can read two stores; a
configured credential binding lets the stored deploy key authenticate as `ops-admin`,
which reads a third store (a second-level surviving credential).

The action scenario is `action:acme/build-helper@v1`. Fixture values are identifiers
only; no credential value is present. Reviewed goldens are `tests/golden/fx16-*`.
