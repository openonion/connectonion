"""Read-only inspections with explicit SNMPv3 and host-verified SSH sources."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
import time

from .synology_transport import command_budget, SynologyError

SYSTEM = '1.3.6.1.4.1.6574.1'
DISKS = '1.3.6.1.4.1.6574.2.1.1'
RAID = '1.3.6.1.4.1.6574.3.1.1'
INTERFACES = '1.3.6.1.2.1.2.2.1'
IPV4 = '1.3.6.1.2.1.4.20.1.2'
MAX_VALUES = 10000
MAX_BYTES = 2 * 1024 * 1024


def checked_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspection_state(name: str, data: dict) -> tuple[str, str]:
    """Observed warnings and missing fields are independent of source availability."""
    rows=data.get('items',data.get('interfaces',[data]))
    warning=False
    partial=False
    for row in rows:
        for key in ('health','deployment','system_partition','power','system_fan','cpu_fan','link'):
            value=row.get(key)
            if value is not None and value not in {'normal','up','initialized'}:
                warning=True
        if row.get('unavailable') or any(row.get(key) is None for key in {
                'disks':('health',),'storage':('health',),'network':('link',),
                'device':('model','dsm_version','system_partition')}.get(name,())):
            partial=True
    return ('warning' if warning else 'partial' if partial else 'available',
            'partial' if partial else 'complete')


def _state(value, labels: dict):
    return labels.get(value, f'unknown({value})') if value is not None else None


def _table(values: dict, prefix: str) -> list:
    rows = {}
    for oid, value in values.items():
        if oid.startswith(prefix + '.'):
            column, _, index = oid[len(prefix) + 1:].partition('.')
            if column.isdigit() and index:
                rows.setdefault(index, {'index':index})[int(column)] = value
    return [rows[index] for index in sorted(rows, key=lambda x: tuple(map(int, x.split('.'))))]


def system_fields(values: dict) -> dict:
    names = {'model':'5.1', 'dsm_version':'5.3', 'temperature_c':'2', 'system_partition':'1',
             'power':'3', 'system_fan':'4.1', 'cpu_fan':'4.2', 'thermal_status':'8'}
    result = {name:values.get(f'{SYSTEM}.{suffix}.0') for name,suffix in names.items()}
    for name in ('system_partition','power','system_fan','cpu_fan'):
        result[name] = _state(result[name], {1:'normal',2:'failed'})
    return result


def disk_rows(values: dict) -> list:
    result = []
    for item in _table(values, DISKS):
        row = {'index':item['index'], 'name':item.get(12, item.get(2)), 'model':item.get(3),
               'type':item.get(4), 'temperature_c':item.get(6), 'bad_sectors':item.get(9),
               'remaining_life':item.get(11),
               'deployment':_state(item.get(5), {1:'normal',2:'initialized',3:'not_initialized',
                                               4:'system_partition_failed',5:'crashed',6:'disconnected'}),
               'health':_state(item.get(13), {1:'normal',2:'warning',3:'critical',4:'failing'})}
        row['unavailable'] = [key for key in ('health','model','type','bad_sectors','remaining_life') if row[key] is None]
        result.append(row)
    return result


def storage_rows(values: dict) -> list:
    labels = dict(enumerate(['normal','repairing','migrating','expanding','deleting','creating',
                            'syncing','parity_checking','assembling','canceling','degraded','crashed',
                            'scrubbing','deploying','undeploying','mounting_cache','unmounting_cache',
                            'expansion_interrupted','shr_converting','shr_migrating','unknown'], 1))
    rows = []
    for item in _table(values, RAID):
        free, total = item.get(4), item.get(5)
        valid = isinstance(free, int) and isinstance(total, int) and 0 <= free <= total and total > 0
        rows.append({'index':item['index'], 'name':item.get(2), 'health':_state(item.get(3), labels),
                     'free':free, 'total':total, 'capacity_unit':'provider_units',
                     'used_percent':round((total-free)/total*100, 2) if valid else None})
    return rows


def network_rows(values: dict) -> list:
    labels = {1:'up',2:'down',3:'testing',4:'unknown',5:'dormant',6:'not_present',7:'lower_layer_down'}
    addresses = {}
    for oid, value in values.items():
        if oid.startswith(IPV4 + '.'):
            addresses.setdefault(str(value), []).append(oid[len(IPV4)+1:])
    return [{'index':row['index'], 'name':row.get(2), 'admin':_state(row.get(7), labels),
             'link':_state(row.get(8), labels), 'ipv4':addresses.get(row['index'], []),
             'speed_bps':row.get(5), 'mtu':row.get(4)} for row in _table(values, INTERFACES)]


async def _snmp_walk(config: dict, secret: dict, roots: list, timeout: float) -> dict:
    try:
        from pysnmp.hlapi.v3arch import asyncio as snmp
    except ImportError:
        raise SynologyError('Install connectonion[synology] for SNMP inspections.', 'source_unavailable') from None
    auth = {'SHA':snmp.USM_AUTH_HMAC96_SHA, 'SHA256':snmp.USM_AUTH_HMAC192_SHA256}
    if (config.get('auth_protocol', 'SHA256') not in auth or config.get('priv_protocol', 'AES128') != 'AES128'
            or not all(config.get(key) for key in ('host','username'))
            or not all(secret.get(key) for key in ('snmp_auth','snmp_priv'))):
        raise SynologyError('Configure an explicit SNMPv3 authPriv account (SHA/SHA256 and AES128) during login.', 'source_setup_required')
    engine = snmp.SnmpEngine()
    values, size = {}, 0
    try:
        async def collect():
            nonlocal size
            target = await snmp.UdpTransportTarget.create((config['host'], config.get('port',161)),
                                                          timeout=min(timeout,5), retries=0)
            user = snmp.UsmUserData(config['username'], secret['snmp_auth'], secret['snmp_priv'],
                                   authProtocol=auth[config.get('auth_protocol','SHA256')],
                                   privProtocol=snmp.USM_PRIV_CFB128_AES)
            for root in roots:
                async for indication, status, _, bindings in snmp.walk_cmd(
                        engine, user, target, snmp.ContextData(contextName=config.get('context','')),
                        snmp.ObjectType(snmp.ObjectIdentity(root)), lookupMib=False, lexicographicMode=False):
                    if indication or status:
                        raise SynologyError('SNMP inspection failed; verify its read-only grant and connectivity.', 'source_unavailable')
                    for oid, value in bindings:
                        key = str(oid)
                        if not key.startswith(root + '.'):
                            continue
                        rendered = value.prettyPrint()
                        size += len(key) + len(rendered.encode('utf-8'))
                        if size > MAX_BYTES or len(values) >= MAX_VALUES:
                            raise SynologyError('SNMP inspection exceeded its result limit.', 'response_too_large')
                        values[key] = int(value) if value.__class__.__name__ in {
                            'Integer','Integer32','Counter32','Counter64','Gauge32','Unsigned32','TimeTicks'} else rendered
        await asyncio.wait_for(collect(), timeout)
    except SynologyError:
        raise
    except (TimeoutError, asyncio.TimeoutError):
        raise SynologyError('SNMP inspection exceeded the command waiting budget.', 'timeout') from None
    except Exception:
        raise SynologyError('SNMP could not inspect the configured source.', 'source_unavailable') from None
    finally:
        engine.close_dispatcher()
    return values


def snmp_values(config: dict, secret: dict, roots: list, timeout: float) -> dict:
    # An SDK caller in an event loop must not block that loop with asyncio.run.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_snmp_walk(config, secret, roots, timeout))
    raise SynologyError('Run synchronous NAS inspections in a worker thread when using an async application.', 'source_setup_required')


def service_rows(all_output: bytes, running_output: bytes) -> list:
    def names(raw):
        try:
            lines = raw.decode('utf-8').splitlines()
        except UnicodeError:
            raise SynologyError('Service enumeration returned invalid text.', 'invalid_response') from None
        if any(not re.fullmatch(r'[A-Za-z0-9_.@:-]{1,256}', line.strip()) for line in lines if line.strip()):
            raise SynologyError('The NAS service enumerator format is unsupported.', 'unsupported_source')
        return set(line.strip() for line in lines if line.strip())
    all_names, running = names(all_output), names(running_output)
    if not running <= all_names:
        raise SynologyError('Service enumeration changed or returned inconsistent results; refresh it.', 'incomplete_inspection')
    return [{'name':name, 'running':name in running} for name in sorted(all_names)]


def ssh_services(config: dict, timeout: float) -> list:
    try:
        import paramiko
    except ImportError:
        raise SynologyError('Install connectonion[synology] for SSH inspections.', 'source_unavailable') from None
    if not all(config.get(key) for key in ('host','username','key_file','known_hosts')):
        raise SynologyError('Configure an SSH key and known-host file during login; no host keys are enrolled automatically.', 'source_setup_required')
    deadline = time.monotonic() + timeout
    def remaining():
        value = deadline-time.monotonic()
        if value <= 0:
            raise SynologyError('SSH inspection exceeded the command waiting budget.', 'timeout')
        return value
    client = paramiko.SSHClient()
    try:
        client.load_host_keys(str(Path(config['known_hosts']).expanduser()))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(config['host'], port=config.get('port',22), username=config['username'],
                       key_filename=str(Path(config['key_file']).expanduser()), timeout=remaining(),
                       auth_timeout=remaining(), banner_timeout=remaining(), look_for_keys=False, allow_agent=False)
        outputs = []
        for command in ('/usr/syno/sbin/synoservice --list', '/usr/syno/sbin/synoservice --list running'):
            channel = client.get_transport().open_session(timeout=remaining())
            try:
                channel.settimeout(remaining())
                channel.exec_command(command)
                stdout, stderr = bytearray(), bytearray()
                while True:
                    remaining()
                    if channel.recv_ready():
                        stdout.extend(channel.recv(65536))
                    if channel.recv_stderr_ready():
                        stderr.extend(channel.recv_stderr(65536))
                    if len(stdout) + len(stderr) > MAX_BYTES:
                        raise SynologyError('Service enumeration exceeded its output limit.', 'response_too_large')
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        break
                    time.sleep(min(.02, remaining()))
                if channel.recv_exit_status() != 0 or stderr:
                    raise SynologyError('The configured SSH account cannot run the documented synoservice read commands.', 'unsupported_source')
                outputs.append(bytes(stdout))
            finally:
                channel.close()
        return service_rows(*outputs)
    except SynologyError:
        raise
    except Exception:
        raise SynologyError('SSH inspection failed; verify host keys, the selected key and its read permissions.', 'source_unavailable') from None
    finally:
        client.close()


class InspectionMixin:
    def _inspect_snmp(self, roots: list) -> dict:
        config = self.profile.get('snmp')
        if not config:
            raise SynologyError('SNMP inspections need an explicitly configured read-only SNMPv3 account in co syno login.', 'source_not_configured')
        values = snmp_values(config, self.secret, roots, self._remaining())
        if not values:
            raise SynologyError('The configured SNMP source returned no supported indicators.', 'unsupported_source')
        return values

    @command_budget
    def connectivity(self) -> dict:
        started = time.monotonic()
        info = self._request('SYNO.FileStation.Info', 'get')
        self._request('SYNO.FileStation.List', 'list_share', limit=1)
        return {'connected':True, 'authenticated':True, 'tls_verified':True, 'endpoint':self.url,
                'hostname':info.get('hostname'), 'request_ms':round((time.monotonic()-started)*1000,2),
                'source':'HTTPS File Station Info/List', 'checked_at':checked_at()}

    @command_budget
    def network_status(self) -> dict:
        client = self.connectivity()
        rows = network_rows(self._inspect_snmp([INTERFACES, IPV4]))
        if not rows:
            raise SynologyError('No NAS interfaces were reported by IF-MIB.', 'unsupported_source')
        return {'client':client, 'interfaces':rows, 'source':'SNMPv3 IF-MIB / IP-MIB (IPv4)',
                'ipv6':'unavailable', 'checked_at':checked_at()}

    @command_budget
    def storage_status(self) -> dict:
        rows = storage_rows(self._inspect_snmp([RAID]))
        return {'items':rows, 'source':'SNMPv3 SYNOLOGY-RAID-MIB', 'topology':'unavailable',
                'checked_at':checked_at()}

    @command_budget
    def storage_disks(self) -> dict:
        rows = disk_rows(self._inspect_snmp([DISKS]))
        return {'items':rows, 'source':'SNMPv3 SYNOLOGY-DISK-MIB', 'checked_at':checked_at()}

    @command_budget
    def service_list(self, running: bool = False) -> dict:
        config = self.profile.get('ssh')
        if not config:
            raise SynologyError('Service inspection needs explicit SSH key and known-host settings in co syno login.', 'source_not_configured')
        rows = ssh_services(config, self._remaining())
        return {'items':[row for row in rows if row['running'] or not running],
                'source':'SSH synoservice --list / --list running', 'checked_at':checked_at()}

    @command_budget
    def status(self) -> dict:
        checks = {}
        inspections = {'connectivity':self.connectivity, 'device':lambda:system_fields(self._inspect_snmp([SYSTEM])),
                       'network':self.network_status, 'storage':self.storage_status,
                       'disks':self.storage_disks, 'services':self.service_list}
        for name, inspect in inspections.items():
            try:
                data=inspect()
                state,completeness=inspection_state(name,data)
                checks[name] = {'state':state, 'completeness':completeness, 'data':data}
            except SynologyError as error:
                checks[name] = {'state':'unavailable', 'completeness':'partial', 'error':{'code':error.code, 'message':str(error)}}
        return {'profile':self.profile.get('name'), 'account':self.account, 'checks':checks,
                'completeness':'complete' if all(c['completeness']=='complete' for c in checks.values()) else 'partial',
                'warnings':[name for name,check in checks.items() if check['state']=='warning'],
                'checked_at':checked_at()}
