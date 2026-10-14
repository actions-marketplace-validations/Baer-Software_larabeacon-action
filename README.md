# LaraBeacon GitHub Action

[![Action tests](https://github.com/Baer-Software/larabeacon-action/actions/workflows/tests.yml/badge.svg)](https://github.com/Baer-Software/larabeacon-action/actions/workflows/tests.yml)

Audit a Laravel application's production readiness on pushes and pull requests. This composite action runs [LaraBeacon Core](https://github.com/A-Baer/LaraBeacon) in CI mode, exports a report, uploads it even when findings block the build, and then enforces the selected findings policy.

No LaraBeacon Cloud account or token is required. This action never passes `--report` and never sends results to LaraBeacon Cloud. Reports are uploaded to GitHub as artifacts by default; Code Scanning upload is opt-in. Reports can contain paths and diagnostic details; set `upload-artifact: 'false'` to keep them on the runner only.

## Prerequisites

- GitHub.com with a Linux or macOS runner and Bash. Windows and GitHub Enterprise Server are not supported in v1.
- Checkout the application and prepare PHP, Composer dependencies and Laravel configuration before this action runs.
- Install **LaraBeacon Core 3.1.0 or newer** as a development dependency in the application and commit the Composer files:

  ```bash
  composer require --dev baer-software/larabeacon:^3.1
  ```

- The application must boot successfully with its CI configuration. Prepare required database/cache/services as for your existing Laravel test workflow. The action does not create an `.env`, generate an application key, run migrations, install packages or change application configuration.

CI mode selects CI-safe analyzers. A passing result covers only the executed checks; it is not a full audit of a running production environment. Reportable analyzer execution errors also block the scan.

## Basic workflow

Add the action after your existing Laravel setup, or adapt this example for a fresh Laravel 12 application (including its database and services):

```yaml
name: LaraBeacon
on: [push, pull_request]
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: shivammathur/setup-php@eb7c497e18156a6bbabfef1d3a82760b9eda3962 # v2
        with:
          php-version: '8.3'
          coverage: none
      - run: composer install --no-interaction --prefer-dist --no-progress
      - name: Prepare Laravel
        run: |
          cp .env.example .env
          php artisan key:generate --no-interaction
      - name: Audit
        uses: Baer-Software/larabeacon-action@v1
        with:
          fail-on: major
```

For reproducibility, pin this action to the full commit SHA shown on its versioned release. `v1` is the supported major-version alias; `v1.0.0` identifies the first release. Configure branch protection to require the audit job if you want findings to block merges.

## Known findings and baselines

Generate and review a baseline locally, then commit it with the application:

```bash
php artisan larabeacon:baseline --profile=ci \
  --output=larabeacon-baseline.json \
  --reason="Known debt scheduled for remediation"
```

```yaml
- uses: Baer-Software/larabeacon-action@v1
  with:
    baseline: larabeacon-baseline.json
    only-new: 'true'
    fail-on: major
```

Accepted findings stay in reports. A baseline changes the gate only when `only-new` is enabled. Execution errors cannot be accepted through the baseline. Do not regenerate baselines automatically in CI.

## GitHub Code Scanning (optional)

SARIF is exported by default. To additionally display results as GitHub Code Scanning alerts, enable this upload and grant the job the required permissions:

```yaml
permissions:
  contents: read
  security-events: write
  actions: read
# In your prepared Laravel job:
steps:
  # ... checkout, PHP, Composer and Laravel setup ...
  - uses: Baer-Software/larabeacon-action@v1
    with:
      upload-sarif: 'true'
```

Code Scanning must be available and enabled for the repository. Private/internal repositories require GitHub Code Security. Organization policies and fork/Dependabot token restrictions can affect uploads; leave this option disabled where it is unavailable and use artifacts instead. An upload failure fails the action. See [GitHub's SARIF upload documentation](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file).

For Laravel in a subdirectory, set `working-directory: backend`. SARIF locations are resolved against that application directory. Give each matrix job/scan a unique `artifact-name`, e.g. `larabeacon-${{ matrix.php }}`. Separate applications use separate Code Scanning categories based on their working directory.

## Inputs

| Input | Default | Behavior |
| --- | --- | --- |
| `working-directory` | `.` | Application directory relative to checkout; must stay inside checkout. |
| `fail-on` | `major` | Minimum blocking severity: `info`, `minor`, `major`, `critical`. |
| `baseline` | empty | Existing baseline file path relative to application directory (absolute paths also accepted). |
| `only-new` | `'false'` | Require a baseline and block only unaccepted findings. |
| `format` | `sarif` | `sarif`, `json` or `markdown`. |
| `upload-artifact` | `'true'` | Upload the generated report as a GitHub artifact. |
| `artifact-name` | `larabeacon-report` | Unique artifact name for this job/scan. |
| `upload-sarif` | `'false'` | Upload to Code Scanning; requires `format: sarif`. |

Boolean inputs accept only `'true'` and `'false'`. Unknown severity/format and invalid prerequisites fail before scanning. Arbitrary command-line arguments are intentionally not exposed; configure analyzers in the application's `config/larabeacon.php`.

## Outputs and failure behavior

| Output | Meaning |
| --- | --- |
| `exit-code` | Scanner exit status: `0` passed, `1` blocking findings or execution errors, `2` invalid scanner configuration; other codes indicate a scanner crash/failure. Empty if input validation or setup failed before scanning. |
| `report-path` | Absolute path to a fresh report on the runner, or empty if none was generated. |
| `artifact-id` | Uploaded GitHub artifact ID, or empty if no upload completed. |
| `sarif-id` | GitHub Code Scanning upload ID, or empty if no upload completed. |

Uploads run before the final policy gate, so blocking findings preserve reports. The action fails for any nonzero scanner exit status, a missing report after a successful scan, invalid inputs or failed uploads. It never converts a scanner failure into a passing gate. To inspect outputs after a failure, subsequent steps need `if: ${{ !cancelled() }}`; workflow-level `continue-on-error` opts out of enforcement and should only be used deliberately.

## Development and license

```bash
bash -n scripts/scan.sh
python3 -m unittest discover -s tests -v
```

CI tests input handling and scanner outcomes on Linux/macOS, runs the actual composite action against a real Laravel application, and verifies that a controlled failing scan fails the action after producing its report.

The action wrapper is MIT licensed. LaraBeacon Core remains LGPL-3.0-or-later and is installed separately by the consuming application. Commercial Pro analyzers retain their own licensing; this action does not distribute them or manage Pro credentials.
