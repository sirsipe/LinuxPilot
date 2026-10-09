import json
import unittest

from uiautomation.protocol import parse_action, pixel_action, system_prompt, validate_action


class ProtocolTests(unittest.TestCase):
    def test_reasoning_and_fenced_json(self):
        action = {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close dialog'}
        response = '<think>Thinking</think>\n```json\n' + json.dumps(action) + '\n```'
        self.assertEqual(parse_action(response), action)

    def test_no_code_or_extra_arguments(self):
        for action in [{'action': 'shell', 'command': 'rm -rf /'},
                       {'action': 'wait', 'seconds': 1, 'reason': '', 'command': 'echo hi'}]:
            with self.assertRaises(ValueError):
                validate_action(action)

    def test_invalid_clicks_and_types(self):
        base = {'action': 'click', 'x': 20, 'y': 30, 'button': 'left', 'count': 1, 'reason': ''}
        for changes in [{'x': True}, {'y': 2.5}, {'button': 'unknown'}, {'count': 900}]:
            with self.assertRaises(ValueError):
                validate_action({**base, **changes})

    def test_wait_and_nonfinite_values(self):
        for seconds in [-1, 6, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                validate_action({'action': 'wait', 'seconds': seconds, 'reason': ''})

    def test_truncated_reasoning_cannot_act(self):
        with self.assertRaises(ValueError):
            parse_action('<think>unfinished')

    def test_qwen_prefilled_reasoning_and_literal_marker(self):
        action = {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Close dialog'}
        self.assertEqual(parse_action('Thinking without an opening tag\n</think>\n' +
                                      json.dumps(action)), action)
        action['reason'] = 'Literal </think> in JSON is data'
        self.assertEqual(parse_action(json.dumps(action)), action)

    def test_selector_click_gets_specific_correction(self):
        with self.assertRaisesRegex(ValueError, 'Use action "press"'):
            parse_action(json.dumps({'action': 'click', 'app': 'Carla2',
                                     'selector': 'button[name="Add Plugin"]', 'reason': 'Open'}))

    def test_run_coordinates_land_on_observed_buttons(self):
        for x, y, bounds in [(408, 95, (473, 61, 109, 32)),
                             (700, 712, (859, 558, 80, 24))]:
            action = {'action': 'click', 'reason': '', 'x': x, 'y': y,
                      'button': 'left', 'count': 1}
            converted = pixel_action(action, 1280, 800)
            bx, by, w, h = bounds
            self.assertTrue(bx <= converted['x'] < bx + w)
            self.assertTrue(by <= converted['y'] < by + h)
            self.assertEqual((action['x'], action['y']), (x, y))

    def test_drag_endpoints_edges_and_scroll_deltas(self):
        drag = {'action': 'drag', 'reason': '', 'x': 500, 'y': 500,
                'to_x': 1000, 'to_y': 1000}
        self.assertEqual(pixel_action(drag, 1280, 800),
                         {**drag, 'x': 640, 'y': 400, 'to_x': 1279, 'to_y': 799})
        scroll = {'action': 'scroll', 'reason': '', 'x': 500, 'y': 500, 'dx': 12, 'dy': -200}
        self.assertEqual(pixel_action(scroll, 1280, 800), {**scroll, 'x': 640, 'y': 400})

    def test_coordinate_modes_and_range_validation(self):
        action = {'action': 'click', 'reason': '', 'x': 1100, 'y': 700,
                  'button': 'left', 'count': 1}
        self.assertEqual(pixel_action(action, 1280, 800, 'pixels'), action)
        with self.assertRaisesRegex(ValueError, 'Normalized positions'):
            pixel_action(action, 1280, 800)
        for changes in ({'x': -1}, {'x': 1280}, {'y': 800}):
            with self.assertRaises(ValueError):
                pixel_action({**action, **changes}, 1280, 800, 'pixels')
        self.assertIn('normalized', system_prompt())
        self.assertIn('Do not normalize', system_prompt('pixels'))

    def test_finish_requires_evidence_and_known_status(self):
        with self.assertRaises(ValueError):
            validate_action({'action': 'finish', 'status': 'passed', 'summary': 'Fine', 'reason': ''})
        with self.assertRaises(ValueError):
            validate_action({'action': 'finish', 'status': 'ok', 'summary': 'Fine',
                             'evidence': 'Saw it', 'reason': ''})
