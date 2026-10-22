"""Render Kubernetes objects using validated, non-secret environment inputs."""
import argparse,json,os,re
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]

def render(e):
    ns=e.get('KUBE_NAMESPACE','cet-time')
    dns=r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?'
    if not re.fullmatch(dns,ns) or len(ns)>63:raise ValueError('KUBE_NAMESPACE must be a DNS label.')
    url=e.get('PUBLIC_URL','').rstrip('/');u=urlsplit(url)
    allow_http=e.get('ALLOW_HTTP','false').lower()
    if allow_http not in ('true','false'):raise ValueError('ALLOW_HTTP must be true or false.')
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:raise ValueError('PUBLIC_URL must be an HTTP(S) origin without a path, query, or credentials.')
    if u.scheme=='http' and allow_http!='true':raise ValueError('HTTP requires ALLOW_HTTP=true; use only for an internal pilot because logins are not encrypted.')
    if u.port is not None:raise ValueError('Use a hostname without an explicit port in PUBLIC_URL.')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',u.hostname) or '.' not in u.hostname:raise ValueError('PUBLIC_URL must use a DNS hostname.')
    # The server compares browser Origin exactly, so do not silently normalize user input.
    if url!=u.scheme+'://'+u.hostname:raise ValueError('PUBLIC_URL must be lowercase scheme://hostname with no explicit port.')
    repo=e.get('IMAGE_REPOSITORY','');host=e.get('REGISTRY_HOST','docker.io')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*(?::[0-9]{1,5})?',host):raise ValueError('REGISTRY_HOST is invalid.')
    if not re.fullmatch(re.escape(host)+r'/[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+',repo):raise ValueError('IMAGE_REPOSITORY must include registry/owner/image, lowercase and without a tag.')
    image=e.get('IMAGE_REF','')
    if not (re.fullmatch(re.escape(repo)+r':[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',image) or re.fullmatch(re.escape(repo)+r'@sha256:[a-f0-9]{64}',image)):raise ValueError('IMAGE_REF must be a tag or digest under IMAGE_REPOSITORY.')
    size=e.get('STORAGE_SIZE','5Gi')
    if not re.fullmatch(r'[1-9][0-9]*(?:Mi|Gi|Ti)',size):raise ValueError('Use a positive STORAGE_SIZE such as 5Gi.')
    for key in ('INGRESS_CLASS','TLS_SECRET_NAME','STORAGE_CLASS','IMAGE_PULL_SECRET'):
        v=e.get(key,'')
        if v and (len(v)>253 or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?',v)):raise ValueError(key+' is not a Kubernetes resource name.')
    enabled=e.get('ENABLE_INGRESS','true').lower()
    if enabled not in ('true','false'):raise ValueError('ENABLE_INGRESS must be true or false.')
    if enabled=='true' and u.scheme=='https' and not e.get('TLS_SECRET_NAME'):raise ValueError('TLS_SECRET_NAME is required for an HTTPS Ingress. For an internal HTTP pilot, set ALLOW_HTTP=true and PUBLIC_URL=http://your-hostname.')
    if u.scheme=='http' and e.get('TLS_SECRET_NAME'):raise ValueError('Leave TLS_SECRET_NAME blank when PUBLIC_URL uses HTTP.')
    items=[]
    for filename in ('pvc.json','configmap.json','deployment.json','service.json'):
        o=json.loads((ROOT/'k8s'/filename).read_text());o['metadata']['namespace']=ns;items.append(o)
    pvc,cfg,dep,service=items
    pvc['spec']['resources']['requests']['storage']=size
    if e.get('STORAGE_CLASS'):pvc['spec']['storageClassName']=e['STORAGE_CLASS']
    cfg['data']['PUBLIC_URL']=url
    cfg['data']['ALLOW_HTTP']=allow_http
    dep['spec']['template']['metadata']['annotations']={'jenkins.io/build':e.get('BUILD_TAG',image)}
    pod=dep['spec']['template']['spec'];pod['containers'][0]['image']=image
    if e.get('IMAGE_PULL_SECRET'):pod['imagePullSecrets']=[{'name':e['IMAGE_PULL_SECRET']}]
    if enabled=='true':
        ing=json.loads((ROOT/'k8s'/'ingress.json').read_text());ing['metadata']['namespace']=ns
        ing['spec']['rules'][0]['host']=u.hostname
        if u.scheme=='https':ing['spec']['tls']=[{'hosts':[u.hostname],'secretName':e['TLS_SECRET_NAME']}]
        else:ing['spec'].pop('tls',None)
        if e.get('INGRESS_CLASS'):ing['spec']['ingressClassName']=e['INGRESS_CLASS']
        items.append(ing)
    return {'apiVersion':'v1','kind':'List','items':items}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    try:payload=render(os.environ)
    except ValueError as e:parser.exit(2,str(e)+'\n')
    Path(args.output).write_text(json.dumps(payload,indent=2)+'\n')
