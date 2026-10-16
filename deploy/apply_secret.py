"""Send Jenkins-bound secrets straight to kubectl; never write them to disk."""
import base64,json,os,subprocess,sys

def payload(e):
    values={k:e.get(k,'') for k in ('ADMIN_PASSWORD','TRELLO_KEY','TRELLO_TOKEN','TRELLO_SECRET')}
    if len(values['ADMIN_PASSWORD'])<12:raise ValueError('ADMIN_PASSWORD must contain at least 12 characters.')
    if any(not v.strip() for v in values.values()):raise ValueError('All four Jenkins application secrets must be configured.')
    return {'apiVersion':'v1','kind':'Secret','metadata':{'name':'cet-time-secrets','namespace':e.get('KUBE_NAMESPACE','cet-time')},'type':'Opaque','data':{k:base64.b64encode(v.encode()).decode() for k,v in values.items()}}
if __name__=='__main__':
    try:data=payload(os.environ)
    except ValueError as e:sys.exit(str(e))
    # Server-side apply avoids embedding a second secret copy in last-applied annotations.
    # Suppress kubectl error bodies, which may include the submitted secret payload.
    result=subprocess.run(['kubectl','apply','--server-side','--field-manager=cet-time-jenkins','-f','-'],input=json.dumps(data).encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if result.returncode:sys.exit('Could not apply cet-time-secrets. Check namespace, RBAC, connectivity, or field ownership; no secret contents were logged.')
    print('Application Secret applied.')
