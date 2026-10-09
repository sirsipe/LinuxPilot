import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from uiautomation.cli import run


class RunnerTests(unittest.TestCase):
    def exercise(self, content, dry_run=False, max_steps=1, observations=None,
                 coordinate_space='normalized', host='carla', planner=False, planner_text_only=False,
                 script_snapshot=False):
        with tempfile.TemporaryDirectory() as root:
            args = argparse.Namespace(structured=False, task='Test Carla', task_file=None,
                max_steps=max_steps, artifacts=root, dry_run=dry_run, settle=0,
                expect_app=None, expect_selector=None, coordinate_space=coordinate_space,
                host=host, planner=planner, planner_text_only=planner_text_only, script_snapshot=script_snapshot)
            desktop = Mock()
            desktop.perform.return_value = None
            desktop.observe.return_value = ({'apps': [], 'image_width': 1280,
                                             'image_height': 800}, b'PNG')
            if observations:
                desktop.observe.side_effect = observations
            model = Mock(name='model')
            model.name = 'holo'
            model.request.return_value = {'choices': [{'message': {'content': content}}]}
            if isinstance(content, list):
                model.request.side_effect = [{'choices': [{'message': {'content': item}}]}
                                             for item in content]
            planner_model = Mock()
            planner_model.name = 'planner'
            planner_model.request.return_value = {'choices': [{'message': {'content': 'Open FX and verify editor title'}}]}
            def choose_model(*args, **kwargs):
                return planner_model if kwargs.get('role') == 'planner' else model
            with patch('uiautomation.cli.Model.from_env', side_effect=choose_model), \
                 patch('uiautomation.desktop.Desktop', return_value=desktop), \
                 redirect_stdout(io.StringIO()):
                code = run(args)
            report = json.loads(next(Path(root).glob('*/report.json')).read_text())
            events = next(Path(root).glob('*/events.jsonl'), None)
            self.events = [json.loads(line) for line in events.read_text().splitlines()] if events else []
            self.requests = model.request.call_args_list
            self.planner_requests = planner_model.request.call_args_list
            return code, report, desktop

    def test_dry_run_delivers_no_input(self):
        action = {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close dialog'}
        code, report, desktop = self.exercise(json.dumps(action), dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(report['proposed_action'], action)
        desktop.perform.assert_not_called()

    def test_invalid_dry_run_does_not_report_success(self):
        code, report, desktop = self.exercise('Some invalid prose', dry_run=True)
        self.assertEqual(code, 2)
        self.assertEqual(report['steps'], 1)
        desktop.perform.assert_not_called()

    def test_delivered_input_is_not_a_test_pass(self):
        action = {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close dialog'}
        code, report, desktop = self.exercise(json.dumps(action))
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'inconclusive')
        desktop.perform.assert_called_once_with(action)

    def test_normalized_action_is_converted_once_and_logged(self):
        action = {'action': 'click', 'reason': 'Add Plugin', 'x': 408, 'y': 95,
                  'button': 'left', 'count': 1}
        _, _, desktop = self.exercise(json.dumps(action))
        desktop.perform.assert_called_once_with({**action, 'x': 522, 'y': 76})
        self.assertEqual(self.events[0]['action'], action)
        self.assertEqual(self.events[0]['pixel_action']['x'], 522)
        self.assertFalse(self.events[0]['ui_changed'])

    def test_pixel_mode_and_dry_run_conversion(self):
        action = {'action': 'click', 'reason': 'Add Plugin', 'x': 527, 'y': 77,
                  'button': 'left', 'count': 1}
        _, _, desktop = self.exercise(json.dumps(action), coordinate_space='pixels')
        desktop.perform.assert_called_once_with(action)
        self.assertIn('Do not normalize', self.requests[0].args[0][0]['content'])
        action.update(x=408, y=95)
        _, report, desktop = self.exercise(json.dumps(action), dry_run=True)
        desktop.perform.assert_not_called()
        self.assertEqual(report['proposed_action'], action)
        self.assertEqual(report['proposed_pixel_action']['x'], 522)

    def test_window_completion_evidence_reaches_next_model_request(self):
        def obs(dialog):
            tree = [{'depth': 1, 'visible': True, 'role': 'window', 'name': 'Carla'}]
            if dialog:
                tree.append({'depth': 1, 'visible': True, 'role': 'dialog', 'name': 'Carla - Add New'})
            return ({'apps': [{'name': 'Carla2', 'tree': tree}],
                     'image_width': 1280, 'image_height': 800}, b'DIALOG' if dialog else b'MAIN')
        actions = [
            {'action': 'press', 'app': 'Carla2', 'selector': 'button[name="Add Plugin"]', 'reason': 'Open'},
            {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close'},
            {'action': 'finish', 'status': 'passed', 'summary': 'Opened and closed',
             'evidence': 'Observed dialog open then closed', 'reason': 'Done'},
        ]
        code, report, _ = self.exercise([json.dumps(a) for a in actions], max_steps=3,
            observations=[obs(False), obs(True), obs(True), obs(False), obs(False), obs(False)])
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(self.events[0]['opened_windows'], [['Carla2', 'dialog', 'Carla - Add New']])
        self.assertEqual(self.events[1]['closed_windows'], [['Carla2', 'dialog', 'Carla - Add New']])
        last_prompt = self.requests[2].args[0][1]['content'][0]['text']
        transitions = json.loads(last_prompt.split(
            'Observed window transitions (verified from fresh accessibility observations): ')[1].split('\n')[0])
        self.assertEqual(transitions[0]['opened'], [['Carla2', 'dialog', 'Carla - Add New']])
        self.assertEqual(transitions[1]['closed'], [['Carla2', 'dialog', 'Carla - Add New']])
        self.assertIn('Visible top-level windows NOW (app, role, name): [["Carla2", "window", "Carla"]]',
                      last_prompt)

    def test_repeated_ineffective_clicks_are_blocked_and_stop(self):
        action = {'action': 'click', 'reason': 'Add Plugin', 'x': 408, 'y': 95,
                  'button': 'left', 'count': 1}
        code, report, desktop = self.exercise(json.dumps(action), max_steps=10)
        self.assertEqual(code, 2)
        self.assertEqual(desktop.perform.call_count, 2)
        self.assertEqual(report['steps'], 5)
        self.assertIn('ineffective', report['summary'])
        self.assertEqual(sum(e.get('executed') is False for e in self.events), 3)
        second_prompt = self.requests[1].args[0][1]['content'][0]['text']
        self.assertIn('No observable change', second_prompt)

    def test_changed_ui_allows_repeating_click(self):
        action = {'action': 'click', 'reason': 'Increment control', 'x': 500, 'y': 500,
                  'button': 'left', 'count': 1}
        def obs(value):
            return ({'apps': [{'value': value}], 'image_width': 1280, 'image_height': 800}, b'PNG')
        # Before/after each input, followed by the final observation.
        snapshots = [obs(0), obs(0), obs(0), obs(1), obs(1), obs(2), obs(2)]
        _, _, desktop = self.exercise(json.dumps(action), max_steps=3, observations=snapshots)
        self.assertEqual(desktop.perform.call_count, 3)
        self.assertEqual([e['ui_changed'] for e in self.events], [False, True, True])

    def test_invalid_action_feedback_contains_rejected_output_and_correction(self):
        content = json.dumps({'action': 'click', 'app': 'Carla2',
                              'selector': 'button[name="Add Plugin"]', 'reason': 'Open'})
        self.exercise(content, max_steps=2)
        prompt = self.requests[1].args[0][1]['content'][0]['text']
        self.assertEqual(self.events[0]['rejected_response'], content)
        self.assertIn('Use action', prompt)
        self.assertIn('press', prompt)

    def test_host_knowledge_and_planner_guidance_reach_vision_actor(self):
        action = {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close dialog'}
        _, report, _ = self.exercise(json.dumps(action), host='reaper', planner=True, dry_run=True)
        self.assertEqual(report['host'], 'reaper')
        self.assertEqual(report['planner_model'], 'planner')
        self.assertIn('testing reaper', self.requests[0].args[0][0]['content'])
        text = self.requests[0].args[0][1]['content'][0]['text']
        self.assertIn('REAPER', text)
        self.assertIn('Open FX and verify editor title', text)
        self.assertEqual(self.planner_requests[0].args[0][1]['content'][1]['type'], 'image_url')
        self.assertFalse(self.planner_requests[0].kwargs['actions'])

    def test_text_only_planner_receives_no_image(self):
        action = {'action': 'wait', 'seconds': 0, 'reason': 'Wait'}
        self.exercise(json.dumps(action), planner=True, planner_text_only=True, dry_run=True)
        self.assertIsInstance(self.planner_requests[0].args[0][1]['content'], str)

    def test_absent_selected_host_cannot_be_reported_passed(self):
        finish = {'action': 'finish', 'status': 'passed', 'summary': 'Done', 'evidence': 'Invented', 'reason': 'Done'}
        observation = ({'apps': [], 'x11_windows': [], 'image_width': 1280, 'image_height': 800}, b'PNG')
        code, report, desktop = self.exercise(json.dumps(finish), observations=[observation, observation], host='reaper')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(self.requests, [])
        desktop.perform.assert_not_called()

    def test_script_capture_failure_overrides_model_pass(self):
        finish = {'action': 'finish', 'status': 'passed', 'summary': 'Done', 'evidence': 'Observed', 'reason': 'Done'}
        with patch('uiautomation.host_scripts.capture_reaper', side_effect=RuntimeError('Snapshot timed out')):
            code, report, _ = self.exercise(json.dumps(finish), host='reaper', script_snapshot=True)
        self.assertEqual(code, 1)
        self.assertEqual(report['model_assessment']['status'], 'passed')
        self.assertEqual(report['status'], 'failed')
        self.assertIn('timed out', report['error'])
