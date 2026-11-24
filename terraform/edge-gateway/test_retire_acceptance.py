"""Offline scope tests for the destructive, one-time acceptance retirement."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('retirement', Path(__file__).with_name('retire-acceptance.py'))
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)


def plan():
    return {'resource_changes': [
        {'address': address, 'mode': 'managed',
         'change': {'actions': ['delete'], 'before': copy.deepcopy(attributes), 'after': None}}
        for address, attributes in retirement.SCOPE.items()]}


class ScopeTests(unittest.TestCase):
    def test_only_the_five_exact_dated_resources_are_accepted(self):
        self.assertEqual(len(retirement.safe_plan(plan())), 5)

    def test_production_ip_rejected_at_the_same_terraform_address(self):
        value = plan()
        resource = next(r for r in value['resource_changes'] if r['address'] == 'hcloud_primary_ip.edge_gateway')
        resource['change']['before']['id'] = '154062800'
        with self.assertRaises(ValueError):
            retirement.safe_plan(value)

    def test_production_dns_zone_and_content_cannot_be_substituted(self):
        for key, value in [('name', 'pz'), ('content', '188.245.252.46'), ('zone_id', 'another-zone')]:
            with self.subTest(key=key):
                candidate = plan()
                candidate['resource_changes'][0]['change']['before'][key] = value
                with self.assertRaises(ValueError):
                    retirement.safe_plan(candidate)

    def test_creations_replacements_and_updates_are_rejected(self):
        for actions in [['create'], ['update'], ['delete', 'create'], ['create', 'delete']]:
            with self.subTest(actions=actions):
                candidate = plan()
                candidate['resource_changes'][0]['change']['actions'] = actions
                with self.assertRaises(ValueError):
                    retirement.safe_plan(candidate)

    def test_vm_or_unrelated_deletion_is_rejected(self):
        for address in ['hcloud_server.edge_gateway[0]', 'hcloud_primary_ip.production', 'kubernetes_namespace.gaming']:
            with self.subTest(address=address):
                candidate = plan()
                candidate['resource_changes'][0]['address'] = address
                with self.assertRaises(ValueError):
                    retirement.safe_plan(candidate)

    def test_new_resource_after_delete_is_rejected(self):
        candidate = plan()
        candidate['resource_changes'][0]['change']['after'] = {'id': 'another-object'}
        with self.assertRaises(ValueError):
            retirement.safe_plan(candidate)

    def test_empty_destroy_scope_supports_already_absent_resources(self):
        self.assertEqual(retirement.safe_plan({'resource_changes': []}), [])

    def test_production_resources_in_the_test_state_are_rejected(self):
        state = {'lineage': 'test', 'serial': 1, 'resources': [{
            'mode': 'managed', 'type': 'hcloud_primary_ip', 'name': 'edge_gateway',
            'instances': [{'attributes': {'id': '154062800', 'name': 'labops-edge-01-ipv4', 'ip_address': '188.245.252.46'}}]}]}
        with self.assertRaises(ValueError):
            retirement.managed(state)


if __name__ == '__main__':
    unittest.main()
