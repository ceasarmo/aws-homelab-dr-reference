"""Trigger native backups over loopback. Never log API keys or response bodies."""
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

TIMEOUT = 300
POLL_SECONDS = 2
CONFIGS = {name: Path('/var/lib')/name/'config.xml' for name in ('radarr','sonarr','prowlarr')}
BAZARR_CONFIG = Path('/opt/bazarr/data/config/config.yaml')


def require(value, message):
    if not value:
        raise RuntimeError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('API redirect refused; review the local base URL.')


def yaml_scalar(text, section, key, default=None):
    # Deliberately narrow reader for ordinary Bazarr-generated YAML scalars.
    # Fail closed on aliases, flow mappings, duplicate keys or complex values.
    blocks = re.findall(r'^'+re.escape(section)+r':\s*\n((?:[ \t]+[^\n]*\n|\n)*)', text+'\n', re.M)
    require(len(blocks) == 1, 'Bazarr configuration section requires review: '+section)
    values = re.findall(r'^  '+re.escape(key)+r':\s*([^\n]*)$', blocks[0], re.M)
    if not values and default is not None:
        return default
    require(len(values) == 1, 'Bazarr configuration field requires review: '+key)
    value = values[0].strip()
    if value.startswith(('"', "'")):
        require(len(value) >= 2 and value[-1] == value[0], 'Unsupported Bazarr scalar.')
        value = value[1:-1]
    require(not any(c in value for c in '\r\n&*!{}[]#'), 'Unsupported Bazarr scalar.')
    return value


class Client:
    def __init__(self, name, port, base, key):
        require(re.fullmatch(r'[A-Za-z0-9]{16,128}',key), name+': invalid API key format.')
        require(str(port).isdigit() and 1 <= int(port) <= 65535, name+': invalid local port.')
        base = base.rstrip('/')
        require(not base or re.fullmatch(r'/[A-Za-z0-9_/-]+',base), name+': unsupported base URL.')
        self.name = name
        self.base = 'http://127.0.0.1:'+str(port)+base+('/api' if name=='bazarr' else '/api/v1' if name=='prowlarr' else '/api/v3')
        self.key = key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def request(self, route, method='GET', body=None):
        headers={'X-Api-Key':self.key,'Accept':'application/json'}
        data=None
        if body is not None:
            data=json.dumps(body).encode();headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base+route,data=data,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=15) as response:
                raw=response.read(4*1024*1024+1)
                require(len(raw)<=4*1024*1024,self.name+': API response too large.')
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(self.name+': API HTTP '+str(exc.code)+'; check local configuration.') from None
        except (urllib.error.URLError,TimeoutError,OSError,ValueError):
            raise RuntimeError(self.name+': API connection or JSON failure; no response content logged.') from None


def clients():
    result={}
    try:
        for name,path in CONFIGS.items():
            xml=ET.parse(path).getroot()
            result[name]=Client(name,xml.findtext('Port',''),xml.findtext('UrlBase','') or '',xml.findtext('ApiKey',''))
        text=BAZARR_CONFIG.read_text()
        result['bazarr']=Client('bazarr',yaml_scalar(text,'general','port','6767'),
                                yaml_scalar(text,'general','base_url',''),yaml_scalar(text,'auth','apikey'))
    except (OSError,ET.ParseError):
        raise RuntimeError('Cannot read native application configuration; review local paths. No keys logged.') from None
    return result


def bazarr_job(client):
    result=client.request('/system/tasks')
    require(isinstance(result,dict) and isinstance(result.get('data'),list),'bazarr: unexpected tasks response.')
    jobs=[job for job in result['data'] if job.get('job_id')=='backup']
    require(len(jobs)==1 and isinstance(jobs[0].get('job_running'),bool),'bazarr: backup task unavailable.')
    return jobs[0]


def check_all():
    all_clients=clients()
    for name,client in all_clients.items():
        if name=='bazarr':
            require(not bazarr_job(client)['job_running'],'bazarr: backup already running.')
        else:
            status=client.request('/system/status')
            require(isinstance(status,dict) and bool(status.get('version')),name+': unknown API status.')
            jobs=client.request('/command')
            require(isinstance(jobs,list),name+': unknown command response.')
            require(not any(str(j.get('name','')).lower()=='backup' and
                    str(j.get('status','')).lower() in ('queued','started') for j in jobs),name+': backup already running.')
            require(isinstance(client.request('/system/backup'),list),name+': unknown backup list.')
    return all_clients


def zip_signature(path):
    st=path.stat()
    return (st.st_size,st.st_mtime_ns)


def validate_zip(path,name):
    require(path.is_file() and not path.is_symlink(),name+': ZIP unavailable.')
    expected={name+'.db','config.yaml' if name=='bazarr' else 'config.xml'}
    with zipfile.ZipFile(path) as z:
        # Require actual DB and configuration, not only a syntactically valid ZIP.
        require(expected.issubset(set(z.namelist())),name+': ZIP missing database/configuration.')
        require(all(z.getinfo(n).file_size>0 for n in expected),name+': ZIP has empty required files.')
        require(z.testzip() is None,name+': ZIP integrity failed.')


def existing_names(folder):
    require(folder.is_dir() and not folder.is_symlink(),'Native backup directory unavailable.')
    return {str(p.relative_to(folder)) for d in [folder,folder/'manual',folder/'scheduled']
            if not d.is_symlink() for p in d.glob('*.zip')}


def run_arr(client,folder):
    old_list=client.request('/system/backup')
    require(isinstance(old_list,list),client.name+': invalid backup list.')
    old={row.get('id') for row in old_list}
    old_names=existing_names(folder)
    started=time.time()
    job=client.request('/command','POST',{'name':'Backup'})
    require(isinstance(job,dict) and type(job.get('id')) is int,client.name+': missing command ID.')
    job_id=job['id']
    deadline=time.monotonic()+TIMEOUT
    while time.monotonic()<deadline:
        state=client.request('/command/'+str(job_id))
        require(isinstance(state,dict) and state.get('id')==job_id,client.name+': command identity mismatch.')
        status=str(state.get('status','')).lower()
        if status=='completed': break
        require(status in ('queued','started'),client.name+': backup failed or unexpected command state.')
        time.sleep(POLL_SECONDS)
    else: raise RuntimeError(client.name+': backup timed out; no retry POST was sent.')
    listing=client.request('/system/backup')
    require(isinstance(listing,list),client.name+': invalid backup list.')
    new=[row for row in listing if row.get('id') not in old and str(row.get('type','')).lower()=='manual']
    require(len(new)==1,client.name+': missing or ambiguous new manual ZIP.')
    filename=new[0].get('name','')
    require(isinstance(filename,str) and re.fullmatch(r'[A-Za-z0-9_.-]+\.zip',filename),client.name+': unsafe ZIP name.')
    path=folder/'manual'/filename
    require(str(path.relative_to(folder)) not in old_names,client.name+': ZIP existed before this request.')
    require(path.resolve().parent==(folder/'manual').resolve() and not (folder/'manual').is_symlink(),client.name+': unsafe ZIP path.')
    require(path.stat().st_mtime>=started-2,client.name+': stale ZIP after command completion.')
    validate_zip(path,client.name)
    return path,{'command_id':job_id,'backup_id':new[0]['id'],'method':'command-api'}


def run_bazarr(client,folder):
    require(not bazarr_job(client)['job_running'],'bazarr: backup already running.')
    old=existing_names(folder)
    started=time.time()
    client.request('/system/tasks','POST',{'taskid':'backup'})
    deadline=time.monotonic()+TIMEOUT
    previous=None
    while time.monotonic()<deadline:
        new=[folder/name for name in existing_names(folder)-old if '/' not in name and name.startswith('bazarr_backup_')]
        require(len(new)<=1,'bazarr: ambiguous new ZIPs; review concurrent backup tasks.')
        if new and not bazarr_job(client)['job_running']:
            path=new[0];signature=zip_signature(path)
            if signature==previous and path.stat().st_mtime>=started-2:
                try:
                    validate_zip(path,'bazarr')
                    return path,{'method':'task-api-new-stable-zip','task_id':'backup'}
                except zipfile.BadZipFile:
                    pass  # File may still be closing; wait within the same deadline.
            previous=signature
        time.sleep(POLL_SECONDS)
    raise RuntimeError('bazarr: no new complete ZIP before timeout; no retry POST was sent.')


def generate(work,folders):
    all_clients=check_all()  # Validate every API before issuing the first POST.
    selected={};evidence={}
    for name,client in all_clients.items():
        print('Generating native backup: '+name,flush=True)
        path,record=(run_bazarr(client,folders[name]) if name=='bazarr' else run_arr(client,folders[name]))
        # Freeze the exact validated result before the next application or Plex stops.
        before=zip_signature(path)
        target=work/(name+'.zip')
        shutil.copyfile(path,target)
        require(before==zip_signature(path),name+': ZIP changed during copying.')
        validate_zip(target,name)
        selected[name]=target
        evidence[name]={**record,'source_name':path.name,'source_modified_epoch':path.stat().st_mtime}
        print('Native backup ready: '+name,flush=True)
    (work/'native-api.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return selected
