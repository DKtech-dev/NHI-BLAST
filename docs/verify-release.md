# Verify a release

Do these checks before you rely on any downloaded artifact. Each one is independent.

## Checksums

```sh
sha256sum -c SHA256SUMS
```

`SHA256SUMS` lists the wheel, the sdist and the Windows executable. It is a transport check,
not a signature. The executable also ships its own `nhi-blast-windows-x64.exe.sha256` record.

## Build provenance

The release workflow attests the wheel and sdist with `actions/attest` (SLSA build
provenance, signed through Sigstore using the workflow's OIDC identity).

```sh
gh attestation verify nhi_blast-0.3.0-py3-none-any.whl --repo DKtech-dev/nhi-blast
```

A successful check shows that the file was built by that repository's workflow; it does not
show that the source is free of defects.

## SBOM

`sbom.cdx.json` is a CycloneDX document generated from a clean environment with the wheel
installed. Inspect it with any CycloneDX tool, for example:

```sh
python -m json.tool sbom.cdx.json | head
```

## What is not claimed

- No independent security audit has been performed.
- PyPI attestations (PEP 740) appear only once the owner has published through a trusted
  publisher.
- Cross-platform behaviour (Linux, macOS) is established only by CI runs, which have to be
  authorised by the owner before they exist.
