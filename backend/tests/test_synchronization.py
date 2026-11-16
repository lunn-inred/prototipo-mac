"""Mesclagem e transporte de sincronização, sem Google nem PostgreSQL reais."""
from copy import deepcopy
import unittest
from uuid import uuid4
from backend.mac_api.modules.backups import sync_data as data, synchronization as sync


class SyncMergeTests(unittest.TestCase):
    def test_three_way_merge_keeps_independent_edits_additions_and_deletions(self):
        base = {'a': {'v': '1'}, 'b': {'v': '2'}, 'deleted': {'v': '3'}}
        local = {'a': {'v': '10'}, 'b': base['b'], 'local': {'v': '4'}}
        remote = {**base, 'b': {'v': '20'}, 'remote': {'v': '5'}}
        self.assertEqual(data.merge(base, local, remote, scope='teste'),
                         {'a': {'v': '10'}, 'b': {'v': '20'}, 'local': {'v': '4'}, 'remote': {'v': '5'}})
        self.assertEqual(data.merge({}, {'x': {'v': '1'}}, {}, scope='teste'), {'x': {'v': '1'}})

    def test_conflicts_include_initial_id_collision_edit_edit_and_edit_delete(self):
        for base, local, remote in [({}, {'id': 'A'}, {'id': 'B'}),
                                   ({'id': 'old'}, {'id': 'A'}, {'id': 'B'}),
                                   ({'id': 'old'}, {}, {'id': 'B'})]:
            with self.subTest(base=base), self.assertRaisesRegex(ValueError, 'Conflito'):
                data.merge(base, local, remote, scope='teste')

    def test_schema_and_view_changes_are_refused_even_when_tables_match(self):
        local = dict(schema={'tables': {}, 'views': ['v1']}, schema_version='one', keys={}, tables={})
        remote = deepcopy(local)
        remote['schema']['views'] = ['v2']
        with self.assertRaisesRegex(ValueError, 'Estrutura incompatível'):
            data.validate(remote, local)

    def test_immutable_commit_chain_refuses_competing_heads_missing_parents_and_cycles(self):
        first, second, competing = [str(uuid4()) for _ in range(3)]
        def entry(identity, parent):
            return dict(id=identity, properties=dict(role='commit', commit=identity, parent=parent))
        class Drive:
            entries = []
            def list(self, **kwargs):
                return self.entries
        drive = Drive()
        drive.entries = [entry(first, 'root'), entry(second, first)]
        self.assertEqual(sync._identity(sync._head(drive)), second)
        for entries in ([entry(first, 'root'), entry(competing, 'root')],
                        [entry(second, first)], [entry(first, second), entry(second, first)]):
            drive.entries = entries
            with self.assertRaises(ValueError):
                sync._head(drive)
