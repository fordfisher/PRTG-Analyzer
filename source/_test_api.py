"""Quick end-to-end test of the status_data upload via the running server."""
import time
import requests

CORE_LOG = (
    '2026-03-01 08:00:00.000000 INFO TId 1000 Core> InitBasics: Logger initialized.\n'
    '2026-03-01 08:00:01.000000 INFO TId 1000 Core> PRTG Network Monitor 26.1.1 core server starting on "test-server"\n'
    '2026-03-01 08:00:02.000000 INFO TId 1000 Core> Objects: 2x Probes, 120x Sensors, 15x Devices\n'
    '2026-03-01 09:00:00.000000 INFO TId 1000 Core> End of log\n'
)

STATUS_PATH = r'c:\Users\blischer\OneDrive - Paessler GmbH\Documents\project_folder\v1.0f\2964866 Support-Bundle - PRTG Status Data (3).htm'

with open(STATUS_PATH, 'rb') as sf:
    resp = requests.post('http://127.0.0.1:8077/api/analyze', files={
        'core_log': ('core.log', CORE_LOG.encode(), 'text/plain'),
        'status_data': ('status.htm', sf, 'text/html'),
    })

print('Upload status:', resp.status_code)
payload = resp.json()
print('job_id:', payload.get('job_id'))
file_hash = payload.get('hash')

time.sleep(2)

result = requests.get(f'http://127.0.0.1:8077/api/result/{file_hash}')
data = result.json()
print('Has status_snapshot:', 'status_snapshot' in data)
if 'status_snapshot' in data:
    snap = data['status_snapshot']
    print('  total_sensors:', snap.get('total_sensors'))
    print('  cpu_load:', snap.get('server_cpu_load_pct'))
    print('  slow_ratio:', snap.get('slow_request_ratio_pct'))
    print('  rps:', snap.get('requests_per_second'))
else:
    print('NO STATUS SNAPSHOT - keys:', list(data.keys()))
