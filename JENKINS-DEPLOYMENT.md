# Deploy ACETime from Jenkins to Kubernetes

The included `Jenkinsfile` checks out this repository, runs the tests, builds and pushes the Docker image, resolves its registry digest, applies configuration and secrets, and waits for Kubernetes rollout. Kubernetes authentication defaults to Jenkins credential **`cet-time`**. No running Jenkins job or cluster has been changed by preparing these files.

## 1. Prepare Jenkins credentials

Create these credentials in the Jenkins folder containing the pipeline job:

| Credential ID | Jenkins kind | Value |
| --- | --- | --- |
| `cet-time` | Secret file | Kubeconfig for the target cluster and namespace |
| Your registry credential ID | Username with password | Registry username and password/access token with push access |
| `cet-time-admin-password` | Secret text | Initial instructor password, at least 12 characters |
| `cet-time-trello-key` | Secret text | Trello application API key |
| `cet-time-trello-token` | Secret text | Trello token with board access and webhook registration permission |
| `cet-time-trello-secret` | Secret text | Trello application secret used to verify webhook signatures |

If your existing `cet-time` credential is a **Kubernetes service-account credential rather than a kubeconfig Secret file**, use Jenkins' Pipeline Syntax generator to replace the file binding with your Kubernetes CLI plugin's `withKubeConfig` binding. Do not paste its token into the Jenkinsfile. This supplied pipeline deliberately uses the standard Secret file binding and requires no Kubernetes Jenkins plugin.

The application Secret is sent directly from bound environment variables to `kubectl` stdin. It is not put in the repository, image, archived manifest, shell arguments, or Jenkins console. The temporary registry login is removed when the push step exits. Run this trusted deployment job on an agent dedicated to trusted jobs; Jenkins credential masking does not isolate credentials from other processes on a shared agent.

## 2. Prepare the cluster once

A cluster administrator should create the namespace (default `cet-time`) and give the kubeconfig identity permissions there. The pipeline never creates namespaces, ClusterRoles, or ClusterRoleBindings.

Required namespace permissions:

| Resource | Verbs |
| --- | --- |
| deployments.apps | get, list, watch, create, update, patch |
| replicasets.apps and pods | get, list, watch |
| services, configmaps, persistentvolumeclaims | get, create, update, patch |
| secrets | get, create, update, patch |
| ingresses.networking.k8s.io | get, create, update, patch, if using the supplied Ingress |

No delete permission is needed. `kubectl apply` does a server-side dry run before workload/secret changes; insufficient access or invalid resource settings fail the job. Pre-create the TLS Secret and registry pull Secret if applicable; the app Secret is pipeline-managed separately.

Use a **block-backed storage class** for SQLite (such as your cluster's vSphere CSI storage class). Do not point this PVC at the NFS storage used for other lab workloads. The app runs as UID/GID 10001; the volume driver must support the pod's fsGroup permissions. The Deployment uses **one replica and Recreate**, with a persistent 5Gi ReadWriteOnce PVC by default. Do not add an HPA or a second replica. ReadWriteOnce restricts node attachment; the one-replica deployment is what prevents concurrent application writers.

## 3. Create the pipeline job

1. Extract this package and place its contents in a Git repository so `Jenkinsfile`, `Dockerfile`, `server.py`, and `k8s/` are at the repository root. Commit all source, including the deployment scripts. Do not commit `.env` or any database.
2. Create a Jenkins **Pipeline** job with **Pipeline script from SCM**, select Git, enter your repository and branch, and set Script Path to `Jenkinsfile`. Use your normal Git credential if the repository is private.
3. Use a Linux agent with `python3` (3.12+), Git, the Docker CLI and access to a Docker daemon, and `kubectl`. Required plugins are Pipeline and Credentials Binding, plus the normal Git/SCM plugins. No root/sudo command is used by the pipeline. If your Jenkins installation labels Docker-capable agents, change `agent any` to your existing label before committing.
4. Edit and commit **`deploy/jenkins.json`** once with the deployment settings below. Jenkins loads this file after checkout on every build; you do not need to fill in **Build with Parameters**. The file is authoritative: old job parameters and environment values for these settings do not override it. On the first run with this Jenkinsfile, Jenkins removes the previous Jenkinsfile-defined parameters; a previously displayed parameter form may still appear until that run completes.

The checked-in file includes `docker.io`, registry credential ID `docker-registry`, kubeconfig ID/namespace `cet-time`, ingress class `nginx`, and storage size `5Gi`. Verify the credential IDs against your Jenkins installation. Fill in `IMAGE_REPOSITORY`, `PUBLIC_URL`, and (with Ingress enabled) `TLS_SECRET_NAME` before building. Those values are deliberately blank because they depend on your actual registry and HTTPS setup. A blank `STORAGE_CLASS` only works with a suitable cluster default or matching pre-provisioned volume; the file does not install a storage driver.

Example settings (replace the example image, hostname, storage class, and Secret names with real ones):

```json
{
  "IMAGE_REPOSITORY": "docker.io/your-account/cet-time",
  "REGISTRY_HOST": "docker.io",
  "REGISTRY_CREDENTIAL_ID": "docker-registry",
  "KUBECONFIG_CREDENTIAL_ID": "cet-time",
  "KUBE_NAMESPACE": "cet-time",
  "PUBLIC_URL": "https://time.your-domain.edu",
  "ENABLE_INGRESS": true,
  "INGRESS_CLASS": "nginx",
  "TLS_SECRET_NAME": "cet-time-tls",
  "STORAGE_CLASS": "your-block-storage-class",
  "STORAGE_SIZE": "5Gi",
  "IMAGE_PULL_SECRET": ""
}
```

Use a JSON boolean for `ENABLE_INGRESS` (`true` or `false`, without quotes). To use an existing external HTTPS reverse proxy, set it to `false`; `TLS_SECRET_NAME` can then be blank. Keep passwords, Trello keys/tokens, kubeconfig contents, and certificate private keys in Jenkins/Kubernetes credentials, never in this JSON file. Only credential IDs and Secret resource names belong here. Unknown keys, incorrect types, and missing required values fail the **Load deployment settings** stage before any image build, registry login, or cluster changes.

You can check the file locally with `python3 deploy/settings.py`; it prints only non-secret environment entries. No additional Jenkins configuration-parsing plugin is needed. Existing SCM/webhook triggers can run this pipeline with the committed settings; this change does not add a new trigger or deploy automatically on every push. To start it manually, use **Build Now** after the parameter definitions have been removed.

| Setting in `deploy/jenkins.json` | Set to |
| --- | --- |
| `IMAGE_REPOSITORY` | Full repository, e.g. `docker.io/YOUR_ORG/cet-time`, lowercase, no tag |
| `REGISTRY_HOST` | `docker.io`, or your matching private registry host |
| `REGISTRY_CREDENTIAL_ID` | Your Jenkins registry username/password credential ID |
| `KUBECONFIG_CREDENTIAL_ID` | `cet-time` (already the default) |
| `KUBE_NAMESPACE` | `cet-time`, or your already-created target namespace |
| `PUBLIC_URL` | Exact external origin, e.g. `https://time.example.edu`; no path or port |
| `ENABLE_INGRESS` | true for the included Ingress; false when using your existing HTTPS reverse proxy |
| `INGRESS_CLASS` | Your controller's class, or blank for the cluster default |
| `TLS_SECRET_NAME` | Existing certificate Secret; required with the supplied Ingress |
| `STORAGE_CLASS` | Your block-backed class, or blank if the cluster default is block-backed |
| `STORAGE_SIZE` | `5Gi` initially; keep this and storage class stable on subsequent builds |
| `IMAGE_PULL_SECRET` | Existing Kubernetes registry pull Secret, if the image is private |

The namespace and deployment are both named `cet-time`; the data claim is `cet-time-data`; the app's secret is `cet-time-secrets`. `k8s/*.json` are standard Kubernetes manifests in JSON syntax. Jenkins passes the loaded settings to `deploy/render.py` without templating secrets. Do not apply the unrendered placeholder files directly.

`PUBLIC_URL` must resolve to your HTTPS entry point and reach this Service. The included Ingress routes `/`, including `/webhook`, to the app. In a MetalLB setup you can keep the application's ClusterIP Service and expose your existing ingress controller through MetalLB. If you already have a proxy route, disable the supplied Ingress and route it to `cet-time.cet-time.svc.cluster.local:80` (adjust namespace as needed). Disabling Ingress omits it from subsequent apply operations; it does not delete an Ingress created by an earlier build. Remove an obsolete route explicitly after reviewing your network configuration.

DNS, certificate issuance, ingress controller installation, storage driver provisioning, and image pull credentials are existing infrastructure prerequisites; this job does not create them.

## 4. Activate the Trello integration

After a successful rollout:

1. Open `PUBLIC_URL` and sign in as `admin` with `cet-time-admin-password`.
2. Open Connections → Load my Trello boards → choose your board.
3. Map **To do: (This Sprint)**, **In process (working)**, **In Process (paused)**, and your completed list. Activate tracking.
4. Register the webhook, then run Refresh & sync. The public callback is `PUBLIC_URL/webhook`; allow Trello's HEAD validation and signed POST deliveries. An institutional interactive sign-in wall must not intercept this route.
5. Create individual student logins linked to Trello members. Assign group members to the Trello card itself. Test a new pilot card through working → paused → working → completed and confirm each student's hours before the first real weekly submission.

The admin password credential initializes the database only once. Updating it in Jenkins and rebuilding does not reset an existing instructor password. Trello credentials are loaded on each rollout; a changed token/key may require re-registering its webhook according to Trello's rules.

## Updates, backups, and troubleshooting

Each image uses a build/commit tag and is deployed by digest. Each build changes a pod-template annotation so updated secrets/configuration are loaded even if application code is unchanged. The job never deletes a PVC, performs automatic rollback, or creates database backups. Back up `/app/data/tracker.db` using SQLite's online backup API or stop the app while copying it. Preserve the PVC when replacing a deployment. Existing Compose volumes from an earlier UID may need ownership migration before reuse; this Kubernetes path starts with a new claim by default.

Rollout failure: inspect `kubectl -n cet-time describe deployment cet-time`, `kubectl -n cet-time get pods,pvc`, pod events, and application logs using an administrator account with appropriate access. Pending pods commonly indicate storage provisioning or registry pull issues. A Secret ownership conflict must be resolved deliberately; the pipeline does not force server-side field ownership. Changing an existing PVC storage class or shrinking a claim is not supported. `Recreate` means updates briefly interrupt the portal; run an instructor history sync after deployment to recover Trello events during that interval.

To return to a previously good image, an authorized operator can run `kubectl -n cet-time rollout undo deployment/cet-time` then `kubectl -n cet-time rollout status deployment/cet-time`. This rolls back the Deployment only: ConfigMaps, Secrets, and the persistent database are not rolled back. Review configuration compatibility first.

Local validation covers application tests and deployment rendering. A live Docker build, Jenkins execution, Kubernetes schema validation, certificate routing, and Trello webhook delivery must be checked on your infrastructure.

## Reference documentation

- Jenkins credentials binding: https://www.jenkins.io/doc/pipeline/steps/credentials-binding/
- Kubernetes CLI plugin, for installations that use withKubeConfig: https://plugins.jenkins.io/kubernetes-cli/
- Kubernetes volume security contexts: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes persistent volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/

## Updating break reminders

Run the pipeline to deploy the break-reminder feature. There are no new Jenkins credentials, environment variables, or migrations. As instructor, open **Break reminders** to change the four-hour default or add a student-specific override. Students enable optional browser notifications in their own signed-in sessions. Keep the app open for reminders; no external messaging service is configured.

