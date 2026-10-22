# Deploy ACETime from Jenkins to Kubernetes

The included `Jenkinsfile` checks out this repository, runs the tests, builds and pushes the Docker image, resolves its registry digest, applies configuration and secrets, and waits for Kubernetes rollout. Kubernetes authentication defaults to Jenkins credential **`cet-time`**. No running Jenkins job or cluster has been changed by preparing these files.

## 1. Prepare Jenkins credentials

Create these credentials in the Jenkins folder containing the pipeline job:

| Credential ID | Jenkins kind | Value |
| --- | --- | --- |
| `cet-time` | Secret file | Kubeconfig for the target cluster and namespace |
| `roseaw-dockerhub` | Username with password | Docker Hub username and password/access token with push access to `cithit/cet-time` |
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
4. The first parameterized run may be needed for Jenkins to expose **Build with Parameters**. Blank required parameters stop validation before any deployment. Fill in the settings below and run it again.

| Job parameter | Set to |
| --- | --- |
| `IMAGE_REPOSITORY` | `docker.io/cithit/cet-time` (configured default); lowercase, no tag |
| `REGISTRY_HOST` | `docker.io`, or your matching private registry host |
| `REGISTRY_CREDENTIAL_ID` | `roseaw-dockerhub` (configured default) |
| `KUBECONFIG_CREDENTIAL_ID` | `cet-time` (already the default) |
| `KUBE_NAMESPACE` | `cet-time`, or your already-created target namespace |
| `PUBLIC_URL` | Exact external origin, e.g. `https://time.example.edu`; no path or port. An HTTP pilot uses `http://time.example.edu` plus `ALLOW_HTTP=true`. |
| `ALLOW_HTTP` | false by default; true permits an internal HTTP pilot without a certificate |
| `ENABLE_INGRESS` | true for the included Ingress; false when using your existing HTTPS reverse proxy |
| `INGRESS_CLASS` | Your controller's class, or blank for the cluster default |
| `TLS_SECRET_NAME` | Existing certificate Secret for HTTPS Ingress; leave blank for an HTTP pilot |
| `STORAGE_CLASS` | Your block-backed class, or blank if the cluster default is block-backed |
| `STORAGE_SIZE` | `5Gi` initially; keep this and storage class stable on subsequent builds |
| `IMAGE_PULL_SECRET` | Existing Kubernetes registry pull Secret, if the image is private |

The namespace and deployment are both named `cet-time`; the data claim is `cet-time-data`; the app's secret is `cet-time-secrets`. `k8s/*.json` are standard Kubernetes manifests in JSON syntax. `deploy/render.py` fills in the job parameters without templating secrets. Do not apply the unrendered placeholder files directly.

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

## Internal pilot without a certificate

HTTPS remains the default. To test before you have a certificate, load the updated Jenkinsfile and use **Build with Parameters**:

- `ALLOW_HTTP`: checked (true).
- `PUBLIC_URL`: `http://YOUR-ACTUAL-DNS-HOSTNAME` (use lowercase and your actual internal DNS name).
- `TLS_SECRET_NAME`: blank.
- `ENABLE_INGRESS`: checked if using your cluster's existing ingress controller; otherwise unchecked when an existing proxy supplies the HTTP route.
- Keep the registry, Kubernetes credential `cet-time`, namespace, and storage settings as configured.

Jenkins may need one run to load the new parameter before it appears. HTTP ingress omits the TLS section. This does not install an ingress controller, configure DNS, or override a controller-wide HTTPS redirect. If your controller forces HTTPS, configure an appropriate HTTP pilot route there or use your existing HTTP reverse proxy. On switching an existing HTTPS app to HTTP, review old HTTPS redirects/HSTS first; fresh pilot installations do not have this issue.

HTTP logins and task data are unencrypted. Restrict this pilot to a trusted internal network and use test accounts/data. In-app reminders work over HTTP; browser notifications and the one-click Clipboard API need HTTPS in normal deployments. For now, select the report's clipboard preview and copy it manually. Move to trusted HTTPS before broader student use. A self-signed certificate is not a substitute for a trusted Trello HTTPS callback.

The app allows signed HTTP webhook callbacks only when `ALLOW_HTTP=true`. Trello must be able to reach the callback and receive HTTP 200 for its HEAD validation; a private internal hostname/IP is not reachable from Trello Cloud. For a private pilot use the instructor's **Refresh & sync** to import card-movement history. Live automatic updates require a reachable callback route. Trello documents HTTP callbacks here: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/ . There is no automatic background Trello polling in this version.

When a trusted certificate is available, change `PUBLIC_URL` to HTTPS, set `TLS_SECRET_NAME` for the Ingress, turn off `ALLOW_HTTP`, and rebuild. Reconfigure any previously registered webhook for the new callback URL; changing the web address does not update it automatically.

Docker Hub is the registry host (`docker.io`); `cithit` is the image namespace. Jenkins uses `roseaw-dockerhub` to authenticate, so the login username need not match the namespace as long as it has push access there. Existing Jenkins job parameters may retain old values after an SCM update: if needed, set `IMAGE_REPOSITORY=docker.io/cithit/cet-time` and `REGISTRY_CREDENTIAL_ID=roseaw-dockerhub` explicitly in Build with Parameters.
