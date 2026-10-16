"""Resolve the pushed digest while preserving the configured registry prefix."""
import json,os,re,subprocess,sys
repo=os.environ['IMAGE_REPOSITORY'];ref=os.environ['IMAGE_REF']
def canonical(s):
    for prefix in ('docker.io/','index.docker.io/'):
        if s.startswith(prefix):return s[len(prefix):]
    return s
r=subprocess.run(['docker','image','inspect',ref],capture_output=True,text=True)
if r.returncode:sys.exit('Could not inspect pushed image.')
images=json.loads(r.stdout)
for entry in images[0].get('RepoDigests',[]):
    name,sep,digest=entry.partition('@')
    if sep and canonical(name)==canonical(repo) and re.fullmatch(r'sha256:[a-f0-9]{64}',digest):
        print(repo+'@'+digest);break
else:sys.exit('No matching pushed repository digest found; deployment stopped.')
