import unittest
from deploy.render import render
from deploy.apply_secret import payload
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.e={'IMAGE_REPOSITORY':'docker.io/example/cet-time','REGISTRY_HOST':'docker.io','IMAGE_REF':'docker.io/example/cet-time@sha256:'+'a'*64,'PUBLIC_URL':'https://time.example.edu','TLS_SECRET_NAME':'time-tls','BUILD_TAG':'jenkins-cet-time-10'}
    def test_storage_identity_and_single_replica(self):
        items={x['kind']:x for x in render(self.e)['items']};d=items['Deployment'];pod=d['spec']['template']['spec']
        self.assertEqual(d['spec']['replicas'],1);self.assertEqual(d['spec']['strategy']['type'],'Recreate')
        self.assertEqual(pod['securityContext']['runAsUser'],10001);self.assertEqual(pod['securityContext']['fsGroup'],10001)
        self.assertEqual(pod['volumes'][0]['persistentVolumeClaim']['claimName'],'cet-time-data')
        self.assertEqual(pod['containers'][0]['image'],self.e['IMAGE_REF']);self.assertEqual(items['PersistentVolumeClaim']['spec']['accessModes'],['ReadWriteOnce'])
        self.assertNotIn('storageClassName',items['PersistentVolumeClaim']['spec'])
        self.assertEqual(items['Ingress']['spec']['tls'][0]['secretName'],'time-tls')
    def test_alternate_namespace_and_external_proxy(self):
        self.e.update(KUBE_NAMESPACE='student-work',ENABLE_INGRESS='false',STORAGE_CLASS='vsphere-block',IMAGE_PULL_SECRET='registry-pull')
        items=render(self.e)['items'];self.assertNotIn('Ingress',[i['kind'] for i in items])
        self.assertTrue(all(i['metadata']['namespace']=='student-work' for i in items))
        self.assertEqual(items[0]['spec']['storageClassName'],'vsphere-block')
        self.assertEqual(items[2]['spec']['template']['spec']['imagePullSecrets'],[{'name':'registry-pull'}])
    def test_reject_bad_origin_or_unrelated_image(self):
        for k,v in [('PUBLIC_URL','http://time.example.edu'),('PUBLIC_URL','https://time.example.edu/path'),('PUBLIC_URL','https://USER:SECRET@time.example.edu'),('IMAGE_REF','evil/repo:latest'),('KUBE_NAMESPACE','bad; echo secret'),('TLS_SECRET_NAME','')]:
            e=dict(self.e);e[k]=v
            with self.subTest(k=k,v=v),self.assertRaises(ValueError):render(e)
    def test_secrets_do_not_enter_manifests(self):
        self.e.update(ADMIN_PASSWORD='unique-secret-12345',TRELLO_KEY='test-key',TRELLO_TOKEN='test-token',TRELLO_SECRET='test-secret')
        import json
        text=json.dumps(render(self.e));self.assertNotIn('unique-secret',text);self.assertNotIn('test-token',text)
        secret=payload(self.e);self.assertEqual(secret['data']['TRELLO_TOKEN'],'dGVzdC10b2tlbg==');self.assertNotIn('annotations',secret['metadata'])
    def test_docker_hub_digest_normalization(self):
        import contextlib,io,os,runpy,json
        from unittest.mock import patch
        from types import SimpleNamespace
        inspect=SimpleNamespace(returncode=0,stdout=json.dumps([{'RepoDigests':['example/cet-time@sha256:'+'b'*64]}]))
        out=io.StringIO()
        with patch.dict(os.environ,self.e),patch('subprocess.run',return_value=inspect),contextlib.redirect_stdout(out):
            runpy.run_path('deploy/resolve_digest.py',run_name='__main__')
        self.assertEqual(out.getvalue().strip(),'docker.io/example/cet-time@sha256:'+'b'*64)
    def test_missing_secrets_fail(self):
        with self.assertRaises(ValueError):payload({})
if __name__=='__main__':unittest.main()
