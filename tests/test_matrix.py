import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from uiautomation.cli import matrix


class MatrixTests(unittest.TestCase):
    def exercise(self, results, dry_run=False):
        with tempfile.TemporaryDirectory() as root:
            args = argparse.Namespace(artifacts=root, hosts=['carla', 'ardour', 'reaper'], dry_run=dry_run)
            calls = []
            def execute(child):
                calls.append(child)
                result = results[len(calls) - 1]
                if isinstance(result, Exception):
                    raise result
                status, code, interrupted = result
                folder = Path(child.artifacts) / 'run'
                folder.mkdir(parents=True)
                (folder / 'report.json').write_text(json.dumps({'status': status, 'interrupted': interrupted}))
                return code
            with patch('uiautomation.cli.run', side_effect=execute), redirect_stdout(io.StringIO()):
                code = matrix(args)
            report = json.loads(next(Path(root).glob('*/report.json')).read_text())
            return code, report, calls

    def test_partial_host_failure_keeps_other_reports_and_sets_exit_code(self):
        code, report, calls = self.exercise([('passed', 0, False), RuntimeError('Ardour launch failed'),
                                             ('inconclusive', 2, False)])
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(report['results']), 3)
        self.assertIn('report', report['results'][0])
        self.assertIn('launch failed', report['results'][1]['error'])
        self.assertTrue(all(c.launch_host and c.restart for c in calls))
        self.assertEqual([c.host for c in calls], ['carla', 'ardour', 'reaper'])

    def test_interrupt_stops_before_launching_the_next_host(self):
        code, report, calls = self.exercise([('inconclusive', 2, True)])
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)
        self.assertTrue(report['results'][0]['interrupted'])

    def test_dry_run_proposals_succeed_without_claiming_pass(self):
        code, report, _ = self.exercise([('inconclusive', 0, False)] * 3, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'inconclusive')
