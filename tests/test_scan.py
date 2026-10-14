import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'scan.sh'


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'checkout' / 'app with spaces'
        (self.app / 'vendor').mkdir(parents=True)
        (self.app / 'vendor' / 'autoload.php').touch()
        (self.app / 'artisan').write_text('''<?php
file_put_contents(getenv('TEST_ARGUMENTS'), json_encode($argv));
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--output=') && getenv('TEST_REPORT') === 'yes') {
        file_put_contents(substr($arg, 9), '{"version":"2.1.0","runs":[{"results":[{"locations":[{"physicalLocation":{"artifactLocation":{"uri":"app/Models/User.php"}}}]}]}]}');
    }
}
exit((int) getenv('TEST_STATUS'));
''')
        self.env = dict(os.environ, GITHUB_WORKSPACE=str(self.root / 'checkout'),
                        RUNNER_TEMP=str(self.root), GITHUB_OUTPUT=str(self.root / 'output'),
                        GITHUB_STEP_SUMMARY=str(self.root / 'summary'),
                        LB_WORKING_DIRECTORY='app with spaces', LB_FAIL_ON='major',
                        LB_FORMAT='sarif', LB_BASELINE='', LB_ONLY_NEW='false',
                        LB_UPLOAD_ARTIFACT='true', LB_UPLOAD_SARIF='false',
                        TEST_ARGUMENTS=str(self.root / 'arguments'),
                        TEST_REPORT='yes', TEST_STATUS='0')

    def run_scan(self, **overrides):
        return subprocess.run(['bash', str(SCRIPT)], env=dict(self.env, **overrides),
                              capture_output=True, text=True)

    def outputs(self):
        return dict(line.split('=', 1) for line in (self.root / 'output').read_text().splitlines())

    def test_pass_and_report(self):
        self.assertEqual(self.run_scan().returncode, 0)
        output = self.outputs()
        self.assertEqual(output['exit-code'], '0')
        self.assertTrue(Path(output['report-path']).is_file())
        self.assertIn('--profile=ci', json.loads((self.root / 'arguments').read_text()))

    def test_findings_preserve_report_for_upload(self):
        self.assertEqual(self.run_scan(TEST_STATUS='1').returncode, 0)
        self.assertEqual(self.outputs()['exit-code'], '1')
        self.assertTrue(Path(self.outputs()['report-path']).is_file())

    def test_nested_sarif_locations_are_repository_relative(self):
        self.assertEqual(self.run_scan().returncode, 0)
        report = json.loads(Path(self.outputs()['report-path']).read_text())
        location = report['runs'][0]['results'][0]['locations'][0]['physicalLocation']
        self.assertEqual(location['artifactLocation']['uri'], 'app%20with%20spaces/app/Models/User.php')

    def test_root_sarif_locations_are_unchanged(self):
        root = self.root / 'checkout'
        (self.app / 'artisan').rename(root / 'artisan')
        (self.app / 'vendor').rename(root / 'vendor')
        self.assertEqual(self.run_scan(LB_WORKING_DIRECTORY='.').returncode, 0)
        report = json.loads(Path(self.outputs()['report-path']).read_text())
        location = report['runs'][0]['results'][0]['locations'][0]['physicalLocation']
        self.assertEqual(location['artifactLocation']['uri'], 'app/Models/User.php')

    def test_invalid_scanner_configuration_without_report(self):
        self.assertEqual(self.run_scan(TEST_STATUS='2', TEST_REPORT='no').returncode, 0)
        self.assertEqual(self.outputs(), {'exit-code': '2', 'report-path': ''})

    def test_crash_status_preserved(self):
        self.assertEqual(self.run_scan(TEST_STATUS='255', TEST_REPORT='no').returncode, 0)
        self.assertEqual(self.outputs()['exit-code'], '255')

    def test_success_without_report_fails(self):
        self.assertNotEqual(self.run_scan(TEST_REPORT='no').returncode, 0)

    def test_baseline_is_one_argument_and_never_shell_code(self):
        baseline = 'baseline $(touch INJECTED).json'
        (self.app / baseline).write_text('{}')
        self.assertEqual(self.run_scan(LB_BASELINE=baseline, LB_ONLY_NEW='true').returncode, 0)
        args = json.loads((self.root / 'arguments').read_text())
        self.assertIn('--baseline=' + baseline, args)
        self.assertIn('--only-new', args)
        self.assertFalse((self.app / 'INJECTED').exists())

    def test_invalid_inputs_fail_before_scan(self):
        for overrides in [{'LB_ONLY_NEW': 'true'}, {'LB_ONLY_NEW': 'yes'},
                          {'LB_FAIL_ON': 'major; touch INJECTED'}, {'LB_FORMAT': 'xml'},
                          {'LB_FORMAT': 'json', 'LB_UPLOAD_SARIF': 'true'},
                          {'LB_BASELINE': 'missing.json'}, {'LB_UPLOAD_ARTIFACT': 'yes'}]:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.run_scan(**overrides).returncode, 2)
                self.assertFalse((self.root / 'arguments').exists())

    def test_paths_cannot_escape_checkout(self):
        for path in ['../../', str(self.app)]:
            self.assertEqual(self.run_scan(LB_WORKING_DIRECTORY=path).returncode, 2)
        (self.root / 'checkout' / 'escape').symlink_to(self.root)
        self.assertEqual(self.run_scan(LB_WORKING_DIRECTORY='escape').returncode, 2)

    def test_prepared_application_required(self):
        (self.app / 'vendor' / 'autoload.php').unlink()
        self.assertEqual(self.run_scan().returncode, 2)

    def test_formats_and_fresh_report_paths(self):
        paths = []
        for fmt, suffix in [('json', '.json'), ('markdown', '.md'), ('sarif', '.sarif')]:
            (self.root / 'output').write_text('')
            self.assertEqual(self.run_scan(LB_FORMAT=fmt).returncode, 0)
            path = self.outputs()['report-path']
            self.assertTrue(path.endswith(suffix))
            paths.append(path)
        self.assertEqual(len(set(paths)), 3)


if __name__ == '__main__':
    unittest.main()
