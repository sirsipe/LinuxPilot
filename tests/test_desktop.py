import unittest
from unittest.mock import Mock

from uiautomation.desktop import Desktop


class CoordinatesTests(unittest.TestCase):
    def test_pixel_coordinates_use_screenshot_mapping(self):
        desktop = Desktop.__new__(Desktop)
        desktop.shot = Mock(width=1280, height=800)
        desktop.shot.image_to_desktop.return_value = (55, 70)
        self.assertEqual(desktop.point(110, 140), (55, 70))
        desktop.shot.image_to_desktop.assert_called_once_with(110, 140)

    def test_outside_coordinates_never_reach_input(self):
        desktop = Desktop.__new__(Desktop)
        desktop.shot = Mock(width=1280, height=800)
        desktop.input = Mock()
        for x, y in [(-1, 0), (1280, 20), (20, 800)]:
            with self.assertRaises(ValueError):
                desktop.perform({'action': 'click', 'x': x, 'y': y, 'button': 'left', 'count': 1})
        desktop.input.click.assert_not_called()
