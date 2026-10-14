#!/usr/bin/env bash
set -euo pipefail

invalid() { printf '::error::%s\n' "$1" >&2; exit 2; }
case "$LB_FAIL_ON" in info|minor|major|critical) ;; *) invalid 'Invalid fail-on severity.' ;; esac
case "$LB_FORMAT" in sarif|json|markdown) ;; *) invalid 'Invalid report format.' ;; esac
for value in "$LB_ONLY_NEW" "$LB_UPLOAD_ARTIFACT" "$LB_UPLOAD_SARIF"; do
  case "$value" in true|false) ;; *) invalid 'Boolean inputs must be true or false.' ;; esac
done
[[ "$LB_ONLY_NEW" != true || -n "$LB_BASELINE" ]] || invalid 'only-new requires a baseline.'
[[ "$LB_UPLOAD_SARIF" != true || "$LB_FORMAT" == sarif ]] || invalid 'upload-sarif requires sarif format.'
[[ "$LB_WORKING_DIRECTORY" != /* ]] || invalid 'working-directory must be relative to the checkout.'

workspace=$(cd "$GITHUB_WORKSPACE" && pwd -P)
cd "$workspace/$LB_WORKING_DIRECTORY" || invalid 'Laravel working directory does not exist.'
application=$(pwd -P)
case "$application/" in "$workspace/"*) ;; *) invalid 'Laravel working directory must stay inside the checkout.' ;; esac
[[ -f artisan && -f vendor/autoload.php ]] || invalid 'Prepare Laravel and install Composer dependencies including LaraBeacon before running this action.'
command -v php >/dev/null || invalid 'PHP must be installed before running this action.'
if [[ -n "$LB_BASELINE" ]]; then
  [[ -f "$LB_BASELINE" ]] || invalid 'Baseline file does not exist.'
fi

# Each scan gets a fresh directory so an earlier report can never be uploaded.
report_directory=$(mktemp -d "$RUNNER_TEMP/larabeacon.XXXXXXXX")
case "$report_directory" in *$'\n'*|*$'\r'*) invalid 'Report paths cannot contain newlines.' ;; esac
extension=$LB_FORMAT
[[ "$LB_FORMAT" != markdown ]] || extension=md
report_path="$report_directory/larabeacon.$extension"
arguments=(artisan larabeacon --profile=ci "--fail-on=$LB_FAIL_ON" "--format=$LB_FORMAT" "--output=$report_path" --no-interaction --no-ansi)
[[ -z "$LB_BASELINE" ]] || arguments+=("--baseline=$LB_BASELINE")
[[ "$LB_ONLY_NEW" != true ]] || arguments+=(--only-new)

set +e
php "${arguments[@]}"
scan_status=$?
set -e
if [[ -s "$report_path" && "$LB_FORMAT" == sarif && "$application" != "$workspace" ]]; then
  application_prefix="${application#"$workspace/"}"
  php "$(dirname "${BASH_SOURCE[0]}")/rebase-sarif.php" "$report_path" "$application_prefix"
fi
printf 'exit-code=%s\n' "$scan_status" >> "$GITHUB_OUTPUT"
if [[ -s "$report_path" ]]; then
  printf 'report-path=%s\n' "$report_path" >> "$GITHUB_OUTPUT"
else
  printf 'report-path=\n' >> "$GITHUB_OUTPUT"
  if [[ "$scan_status" == 0 ]]; then
    printf '::error::The scanner returned success without a report. Require LaraBeacon Core 3.1.0 or newer.\n' >&2
    exit 1
  fi
fi
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '### LaraBeacon\n\nScanner exit code: **%s** (0: passed; 1: blocking findings or check errors; 2: invalid configuration).\n\nReport format: **%s**. See the scan log and report for details.\n' "$scan_status" "$LB_FORMAT" >> "$GITHUB_STEP_SUMMARY"
fi
# Uploads run before the final composite step enforces the scanner exit code.
