"""Isolate potentially blocking AT-SPI semantic calls from the observation loop."""
import json
import sys

import xa11y

from .protocol import validate_action


def main():
    a = validate_action(json.load(sys.stdin))
    xa11y.set_default_timeout(3)
    if a['action'] not in ('press', 'focus', 'set_value', 'set_numeric_value'):
        raise ValueError('Worker only supports semantic actions')
    app = xa11y.App.by_name(a['app'])
    locator = app.locator(a['selector'])
    count = locator.count()
    if count != 1:
        raise ValueError(f'Selector matched {count} controls; choose a unique selector '
                         '(use [visible="true"] for hidden Qt dialogs)')
    if a['action'] == 'set_value':
        locator.set_value(a['text'])
    elif a['action'] == 'set_numeric_value':
        locator.set_numeric_value(a['value'])
    else:
        getattr(locator, a['action'])()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
