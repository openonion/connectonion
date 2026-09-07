"""Inspection results distinguish observed indicators from unavailable coverage."""
import pytest

from connectonion.useful_tools.synology_inspections import (
    disk_rows, storage_rows, network_rows, system_fields, service_rows, InspectionMixin,
)
from connectonion.useful_tools.synology_transport import SynologyError


def test_disk_deployment_is_not_a_missing_health_indicator():
    prefix = '1.3.6.1.4.1.6574.2.1.1'
    rows = disk_rows({f'{prefix}.12.0':'Drive 1', f'{prefix}.5.0':1,
                      f'{prefix}.6.0':34, f'{prefix}.13.1':3, f'{prefix}.12.1':'Drive 2'})
    assert rows[0]['deployment'] == 'normal' and rows[0]['health'] is None
    assert rows[0]['unavailable'] == ['health', 'model', 'type', 'bad_sectors', 'remaining_life']
    assert rows[1]['health'] == 'critical'


def test_storage_preserves_provider_rows_without_inventing_topology_or_units():
    p = '1.3.6.1.4.1.6574.3.1.1'
    rows = storage_rows({f'{p}.2.0':'pool', f'{p}.3.0':11, f'{p}.4.0':25, f'{p}.5.0':100,
                         f'{p}.2.1':'volume', f'{p}.3.1':1})
    assert rows[0]['health'] == 'degraded' and rows[0]['used_percent'] == 75
    assert rows[0]['capacity_unit'] == 'provider_units'
    assert rows[1]['free'] is None and rows[1]['used_percent'] is None


def test_network_keeps_admin_and_operational_link_state_separate():
    p = '1.3.6.1.2.1.2.2.1'
    rows = network_rows({f'{p}.2.7':'eth0',f'{p}.7.7':1,f'{p}.8.7':2,
                         '1.3.6.1.2.1.4.20.1.2.192.0.2.7':7})
    assert rows == [{'index':'7','name':'eth0','admin':'up','link':'down',
                     'ipv4':['192.0.2.7'],'speed_bps':None,'mtu':None}]


def test_system_partition_health_does_not_become_overall_health():
    result = system_fields({'1.3.6.1.4.1.6574.1.1.0':1})
    assert result['system_partition'] == 'normal'
    assert result['model'] is None and 'healthy' not in result


def test_service_state_requires_actual_enumeration_and_rejects_inconsistent_lists():
    assert service_rows(b'alpha\nbeta\n', b'beta\n') == [
        {'name':'alpha','running':False}, {'name':'beta','running':True}]
    with pytest.raises(SynologyError, match='inconsistent'):
        service_rows(b'alpha\n', b'unknown\n')


def test_aggregate_cannot_call_missing_monitors_healthy():
    class NAS(InspectionMixin):
        url='https://nas.test'; account='one'; profile={'name':'home'}; secret={}
        def _request(self, *args, **kwargs):
            return {'hostname':'NAS'}
        def _remaining(self):
            return 5
    result = NAS().status()
    assert result['completeness'] == 'partial'
    assert result['checks']['connectivity']['state'] == 'available'
    assert result['checks']['disks']['state'] == 'unavailable'
    with pytest.raises(SynologyError) as error:
        NAS().storage_disks()
    assert error.value.code == 'source_not_configured'


def test_aggregate_reports_warning_and_partial_indicator_coverage():
    class NAS(InspectionMixin):
        account='one'; profile={'name':'home'}
        def connectivity(self):
            return {'connected':True}
        def _inspect_snmp(self,roots):
            return {'1.3.6.1.4.1.6574.1.1.0':2}
        def network_status(self):
            return {'interfaces':[{'link':'down'}]}
        def storage_status(self):
            return {'items':[{'health':'degraded'}]}
        def storage_disks(self):
            return {'items':[{'health':None,'deployment':'normal','unavailable':['health']}]}
        def service_list(self):
            return {'items':[]}
    result=NAS().status()
    assert result['checks']['storage']['state']=='warning'
    assert result['checks']['network']['state']=='warning'
    assert result['checks']['disks']['state']=='partial'
    assert result['completeness']=='partial'
