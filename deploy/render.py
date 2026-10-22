"""Render Kubernetes objects using validated, non-secret environment inputs."""
import argparse,ipaddress,json,os,re
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]

def render(e):
    ns=e.get('KUBE_NAMESPACE','cet-time')
    dns=r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?'
    if not re.fullmatch(dns,ns) or len(ns)>63:raise ValueError('KUBE_NAMESPACE must be a DNS label.')
    enabled=e.get('ENABLE_INGRESS','true').lower()
    if enabled not in ('true','false'):raise ValueError('ENABLE_INGRESS must be true or false.')
    url=e.get('PUBLIC_URL','').rstrip('/');u=urlsplit(url)
    if u.scheme!='http' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:raise ValueError('This deployment is HTTP-only. Set PUBLIC_URL=http://your-hostname without a path, query, or credentials.')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',u.hostname) or '.' not in u.hostname:raise ValueError('PUBLIC_URL must use a DNS hostname or IPv4 address.')
    is_ip=bool(re.fullmatch(r'[0-9.]+',u.hostname))
    if is_ip:ipaddress.IPv4Address(u.hostname)
    port=u.port
    if port is not None and not 1<=port<=65535:raise ValueError('PUBLIC_URL port must be between 1 and 65535.')
    if enabled=='true' and (is_ip or port is not None):raise ValueError('Ingress requires a DNS hostname without an explicit port. Set ENABLE_INGRESS=false for direct LoadBalancer access.')
    # The server compares browser Origin exactly, so do not silently normalize user input.
    canonical='http://'+u.hostname+((':'+str(port)) if port is not None and port!=80 else '')
    if url!=canonical:raise ValueError('PUBLIC_URL must match the browser origin exactly: lowercase http://host[:port], with no explicit default port 80.')
    repo=e.get('IMAGE_REPOSITORY','');host=e.get('REGISTRY_HOST','docker.io')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*(?::[0-9]{1,5})?',host):raise ValueError('REGISTRY_HOST is invalid.')
    if not re.fullmatch(re.escape(host)+r'/[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+',repo):raise ValueError('IMAGE_REPOSITORY must include registry/owner/image, lowercase and without a tag.')
    image=e.get('IMAGE_REF','')
    if not (re.fullmatch(re.escape(repo)+r':[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',image) or re.fullmatch(re.escape(repo)+r'@sha256:[a-f0-9]{64}',image)):raise ValueError('IMAGE_REF must be a tag or digest under IMAGE_REPOSITORY.')
    size=e.get('STORAGE_SIZE','5Gi')
    if not re.fullmatch(r'[1-9][0-9]*(?:Mi|Gi|Ti)',size):raise ValueError('Use a positive STORAGE_SIZE such as 5Gi.')
    for key in ('INGRESS_CLASS','IMAGE_PULL_SECRET','NFS_PV_NAME'):
        v=e.get(key,'')
        if v and (len(v)>253 or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?',v)):raise ValueError(key+' is not a Kubernetes resource name.')
    items=[]
    for filename in ('pvc.json','configmap.json','deployment.json','service.json'):
        o=json.loads((ROOT/'k8s'/filename).read_text());o['metadata']['namespace']=ns;items.append(o)
    pvc,cfg,dep,service=items
    pvc['spec']['resources']['requests']['storage']=size
    pv_name=e.get('NFS_PV_NAME','cet-time-nfs-pv')
    pvc['spec']['volumeName']=pv_name
    pvc['spec']['storageClassName']=''
    server=e.get('NFS_SERVER','10.48.228.25');path=e.get('NFS_PATH','/srv/nfs/roseaw')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]*',server):raise ValueError('NFS_SERVER must be a host or IP address.')
    if not path.startswith('/') or any(c in path for c in ('\n','\r','\x00')):raise ValueError('NFS_PATH must be an absolute export path.')
    manage=e.get('MANAGE_NFS_PV','true').lower()
    if manage not in ('true','false'):raise ValueError('MANAGE_NFS_PV must be true or false.')
    if manage=='true':
        pv=json.loads((ROOT/'k8s'/'pv.json').read_text())
        pv['metadata']['name']=pv_name
        pv['spec']['capacity']['storage']=size
        pv['spec']['nfs']={'server':server,'path':path}
        pv['spec']['claimRef']={'namespace':ns,'name':'cet-time-data'}
        items.insert(0,pv)
    cfg['data']['PUBLIC_URL']=url
    cfg['data']['ALLOW_HTTP']='true'
    dep['spec']['template']['metadata']['annotations']={'jenkins.io/build':e.get('BUILD_TAG',image)}
    pod=dep['spec']['template']['spec'];pod['containers'][0]['image']=image
    if e.get('IMAGE_PULL_SECRET'):pod['imagePullSecrets']=[{'name':e['IMAGE_PULL_SECRET']}]
    if enabled=='true':
        ing=json.loads((ROOT/'k8s'/'ingress.json').read_text());ing['metadata']['namespace']=ns
        ing['spec']['rules'][0]['host']=u.hostname
        ing['spec'].pop('tls',None)
        if e.get('INGRESS_CLASS'):ing['spec']['ingressClassName']=e['INGRESS_CLASS']
        items.append(ing)
    return {'apiVersion':'v1','kind':'List','items':items}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    try:payload=render(os.environ)
    except ValueError as e:parser.exit(2,str(e)+'\n')
    Path(args.output).write_text(json.dumps(payload,indent=2)+'\n')
