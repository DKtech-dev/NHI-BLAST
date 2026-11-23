# NHB-GHA-007: Unconstrained package lifecycle hooks in a privileged job

A job holding `id-token: write` or persistent secrets executes `npm install`, `pnpm install`, or `yarn` without `--ignore-scripts` or immutable/frozen-lockfile flags.

## Remediation

Run package installation in a separate unprivileged job or pass `--ignore-scripts` with frozen/immutable lockfile flags.
