"""Regressão para a view de saltos existente, sem id_atleta."""
import unittest
from unittest.mock import patch

from backend.mac_api.repositories import data_repository as repository


class ViewCompatibilityTests(unittest.TestCase):
    @patch.object(repository, '_fetch_all', return_value=[])
    def test_jump_read_does_not_require_id_column(self, fetch):
        repository.jump_records()
        self.assertNotIn('id_atleta', fetch.call_args.args[0])

    @patch.object(repository, 'list_athletes')
    @patch.object(repository, '_fetch_all')
    def test_editable_collections_only_use_unique_registered_matches(self, fetch, athletes):
        athletes.return_value = [
            {'id_atleta': 1, 'nome': 'José Silva', 'apelido': 'ZE'},
            {'id_atleta': 2, 'nome': 'Ana', 'apelido': 'DUPLO'},
            {'id_atleta': 3, 'nome': 'Maria', 'apelido': 'DUPLO'},
        ]
        fetch.return_value = [{'atleta': name, 'maior_cmj': 30}
                              for name in ['ZE', 'DUPLO', 'DESCONHECIDO']]
        result = repository.jump_collections()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id_atleta'], 1)
        self.assertEqual(result[0]['atleta'], 'José Silva')
        self.assertNotIn('v.id_atleta', fetch.call_args.args[0])
