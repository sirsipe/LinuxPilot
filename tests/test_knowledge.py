import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from uiautomation import knowledge


class KnowledgeTests(unittest.TestCase):
    def fixture(self, root, host=None, dry_run=False):
        run = Path(root) / 'matrix' / (host or 'legacy') / 'run'
        run.mkdir(parents=True)
        report = {'task': 'Open editor', 'status': 'inconclusive', 'dry_run': dry_run}
        if host:
            report['host'] = host
        (run / 'report.json').write_text(json.dumps(report))
        event = {'step': 1, 'action': {'action': 'click'}, 'ui_changed': False,
                 'result': 'No observable change'}
        (run / 'events.jsonl').write_text(json.dumps(event) + '\n')
        for stem in ('001', '001-after'):
            (run / (stem + '.json')).write_text('{"apps": []}')
        (run / '001-after.png').write_bytes(b'PNG')
        return run

    def reviewer(self, content=None):
        model = Mock()
        model.name = 'reviewer'
        model.request.return_value = {'choices': [{'message': {'content': content or json.dumps({
            'lessons': [{'context': 'Editor closed', 'lesson': 'The attempted click had no visible effect; reobserve.',
                         'outcome': 'failure'}]})}}]}
        return model

    def test_nested_matrix_host_isolation_legacy_and_dry_run(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root, 'reaper')
            self.fixture(root)
            self.fixture(root, 'ardour', dry_run=True)
            self.assertEqual(len(list(knowledge.candidates(root, 'reaper'))), 1)
            self.assertEqual(len(list(knowledge.candidates(root, 'carla'))), 1)
            self.assertEqual(list(knowledge.candidates(root, 'ardour')), [])

    def test_update_links_evidence_reuses_context_and_is_incremental(self):
        with tempfile.TemporaryDirectory() as root:
            run = self.fixture(root, 'reaper')
            store = Path(root) / 'knowledge'
            model = self.reviewer()
            result = knowledge.update(store, root, 'reaper', model, Path(root) / 'review')
            self.assertEqual((result['reviewed'], result['added']), (1, 1))
            item = knowledge.context(store, 'reaper', 'editor')['tentative_lessons'][0]
            self.assertEqual(item['confidence'], 'tentative')
            self.assertEqual(item['source']['run'], str(run))
            self.assertEqual(item['source']['event_line'], 1)
            self.assertEqual(item['source']['screenshot_sha256'], knowledge.digest(b'PNG'))
            knowledge.update(store, root, 'reaper', model, Path(root) / 'second-review')
            self.assertEqual(model.request.call_count, 1)
            # Changing evidence invalidates the review identity and permits a new review.
            (run / '001-after.png').write_bytes(b'CHANGED')
            knowledge.update(store, root, 'reaper', model, Path(root) / 'third-review')
            self.assertEqual(model.request.call_count, 2)

    def test_malformed_lessons_are_rejected_without_marking_reviewed(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root, 'reaper')
            result = knowledge.update(Path(root) / 'knowledge', root, 'reaper',
                self.reviewer('{"lessons": [{"lesson": "Invented"}]}'), Path(root) / 'review')
            self.assertEqual(result['added'], 0)
            self.assertEqual(len(result['errors']), 1)
            store = knowledge.read_store(Path(root) / 'knowledge', 'reaper')
            self.assertEqual(store['reviewed'], [])
            self.assertEqual(store['lessons'], [])

    def test_review_request_has_one_after_image_and_uncertain_status(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root, 'reaper')
            model = self.reviewer()
            knowledge.update(Path(root) / 'knowledge', root, 'reaper', model, Path(root) / 'review')
            messages = model.request.call_args.args[0]
            content = messages[1]['content']
            self.assertEqual(len([x for x in content if x['type'] == 'image_url']), 1)
            self.assertIn('not independently verified', content[0]['text'])
            self.assertIn('No observable change', content[0]['text'])

    def test_bounds_and_schema_prevent_unbounded_or_forged_source_fields(self):
        for value in ({'lessons': [{}]}, {'lessons': 'bad'}, {'lessons': [{'context': 'a',
                       'lesson': 'b', 'outcome': 'success', 'source': '/fake'}]},
                      {'lessons': [{'context': 'a', 'lesson': 'x' * 1201, 'outcome': 'uncertain'}]}):
            with self.assertRaises(ValueError):
                knowledge.parse_lessons(json.dumps(value))
