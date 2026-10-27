# Deploy ACETime from Jenkins to Kubernetes

The current deployment is **HTTP-only**, with SQLite stored on your supplied NFS export. The pipeline tests the app, builds and pushes an image, deploys by digest, and waits for rollout.

## Configured defaults

| Setting | Value |
| --- | --- |
| Docker Hub image repository | `docker.io/cithit/cet-time` |
| Jenkins registry credential | `roseaw-dockerhub` |
| Jenkins kubeconfig credential | `cet-time` |
| Kubernetes namespace | `cet-time` |
| NFS server | `10.48.228.25` |
| NFS export | `/srv/nfs/roseaw` |
| App directory inside export | `cet-time` |
| Actual database file on NFS | `/srv/nfs/roseaw/cet-time/tracker.db` |
| PersistentVolume | `cet-time-nfs-pv` |
| PersistentVolumeClaim | `cet-time-data` |
| Reclaim policy | **Retain** |
| Access mode | ReadWriteMany; application remains one replica |
| HTTP Service | `cet-time`, ClusterIP port 80 → container 8080 |
| Public browser origin | `http://10.48.229.63:8080` |
| Ingress | Disabled; existing MetalLB service `cet-time/loadbalancer` supplies external access |

## Prepare NFS once

On the NFS server, create the dedicated app directory with permissions for container UID/GID **10001**. For an administrator on that server:

```sh
sudo install -d -o 10001 -g 10001 -m 2770 /srv/nfs/roseaw/cet-time
```

Do not change ownership recursively on `/srv/nfs/roseaw`; it may contain other applications. The pod mounts only the `cet-time` subdirectory. No root init container or recursive fsGroup ownership change is used. Keep NFS locking enabled; do not use a `nolock` mount. Cluster nodes must be able to reach the export, and the NFS server must grant them read/write access. No NFS protocol version is forced; use the version supported by your server and cluster.

SQLite depends on reliable NFS locking and fsync behavior. DELETE rollback journal mode, synchronous FULL, an in-process DB lock, and one replica reduce contention but do not make unreliable network storage safe. Never mount this database into a second running app, connect an external SQL client to it, or run a second deployment against the same directory. Do not enable WAL or add an HPA. Reference: https://www.sqlite.org/useovernet.html and https://www.sqlite.org/wal.html .

## Prepare Jenkins credentials

| Credential ID | Kind | Contents |
| --- | --- | --- |
| `cet-time` | Secret file | Kubeconfig for the target cluster |
| `roseaw-dockerhub` | Username with password | Docker Hub user/token with push access to `cithit/cet-time` |
| `cet-time-admin-password` | Secret text | Initial instructor password, 12+ characters |
| `cet-time-trello-key` | Secret text | Trello API key |
| `cet-time-trello-token` | Secret text | Trello token with board and webhook access |
| `cet-time-trello-secret` | Secret text | Trello application secret for webhook signatures |

The kubeconfig binding expects a Secret file. If your installation uses another credential kind, use your existing Kubernetes CLI plugin binding instead. The pipeline does not print secrets or store them in source/images; the application Secret goes to kubectl stdin. Use a trusted build agent.

## Cluster permissions

Create the target namespace before running Jenkins. Namespace permissions needed by the kubeconfig identity:

| Resources | Verbs |
| --- | --- |
| deployments.apps | get, list, watch, create, update, patch |
| replicasets.apps, pods | get, list, watch |
| services, configmaps, persistentvolumeclaims, secrets | get, create, update, patch |
| ingresses.networking.k8s.io | get, create, update, patch when Ingress is enabled |

**PersistentVolumes are cluster-scoped.** With `MANAGE_NFS_PV=true`, the kubeconfig also needs get/create/update/patch access to PersistentVolumes. If `cet-time` is namespace-scoped, have a cluster administrator apply `k8s/pv.json` once, then set `MANAGE_NFS_PV=false` in Jenkins. The supplied PV is pre-bound to `cet-time/cet-time-data`; adjust its claimRef if deploying to a different namespace. The pipeline never grants RBAC permissions or creates namespaces.

Retain preserves the exported data if a claim is deleted; it does not back up the database, protect against a user deleting files, or automatically rebind a released PV. Do not delete a PVC to work around a binding error. If a previous claim is already bound with different access modes, storage class, or PV name, preserve it and migrate the database during planned downtime using a separate claim/volume. Kubernetes does not permit arbitrary changes to a bound PVC.

## Jenkins job and parameters

Use a **Pipeline from SCM** job pointing at `https://github.com/miamioh-cit/cet-time.git`, branch `main`, Script Path `Jenkinsfile`. The Linux agent needs Python 3.12+, Git, Docker with daemon access, and kubectl. Required Jenkins plugins are Pipeline, Git, and Credentials Binding. No sudo command is used by the pipeline.

After fetching the updated Jenkinsfile, use **Build with Parameters**:

| Parameter | Setting |
| --- | --- |
| `IMAGE_REPOSITORY` | `docker.io/cithit/cet-time` |
| `REGISTRY_HOST` | `docker.io` |
| `REGISTRY_CREDENTIAL_ID` | `roseaw-dockerhub` |
| `KUBECONFIG_CREDENTIAL_ID` | `cet-time` |
| `KUBE_NAMESPACE` | Existing namespace; default `cet-time` |
| `INGRESS_CLASS` | Your controller's class, or blank for its default |
| `NFS_SERVER` | `10.48.228.25` |
| `NFS_PATH` | `/srv/nfs/roseaw` |
| `NFS_PV_NAME` | `cet-time-nfs-pv`; use a different name for a separately provisioned volume |
| `MANAGE_NFS_PV` | true when Jenkins can apply the PV; false after admin provisioning |
| `STORAGE_SIZE` | `5Gi`; capacity declaration, not an NFS server quota |
| `IMAGE_PULL_SECRET` | Existing namespace Secret if the image is private |

`PUBLIC_URL`, `ENABLE_INGRESS`, `ALLOW_HTTP`, `TLS_SECRET_NAME`, and `STORAGE_CLASS` are retired job parameters for this configuration. The Jenkinsfile environment fixes PUBLIC_URL to `http://10.48.229.63:8080` and ENABLE_INGRESS to `false`, overriding stale build-parameter environment values. HTTP is set directly, no TLS section is generated, and the static PV/PVC both have empty storageClassName. If Jenkins retains old parameter values, refresh the job from SCM; retired HTTP/TLS/storage-class values are ignored. HTTPS PUBLIC_URL values are rejected. Existing job values for image repository/credential can also persist; set them explicitly to the values above if necessary.

The manifests do not install an ingress controller, configure DNS, or override an ingress controller's global HTTPS redirect. If a controller forces HTTPS, configure its HTTP route for this pilot. The included Ingress routes all paths, including `/webhook`, to the app. If using your own proxy, route it to `cet-time.cet-time.svc.cluster.local:80` (adjust namespace if needed). Disabling an already deployed Ingress omits it from future apply operations but does not delete it automatically.

### Existing MetalLB LoadBalancer

The Jenkinsfile environment sets `PUBLIC_URL=http://10.48.229.63:8080` and `ENABLE_INGRESS=false` on every build. These are repository settings, not build parameters, so stale saved Jenkins values cannot restore the old origin. To change the public address later, edit those two settings in the Jenkinsfile. Each deployment writes the origin to `cet-time-config` and rolls out a new pod; a temporary ConfigMap patch is no longer required.

The existing `cet-time/loadbalancer` Service must retain IP `10.48.229.63`, TCP port `8080`, target port `http`, and selector `app.kubernetes.io/name=cet-time`. MetalLB's address pool and L2 advertisement remain in its installation namespace (`default`). Jenkins continues managing the separate internal `cet-time` ClusterIP Service; it does not replace or delete the existing LoadBalancer or install MetalLB.

Open exactly `http://10.48.229.63:8080`. The app compares the browser Origin with `PUBLIC_URL`, including the port. Direct access supports an IPv4 address or DNS hostname with an optional non-default port. Ingress mode requires a DNS hostname without an explicit port. Omit `:80` for HTTP because browsers omit that default port from the Origin header.

## Storage check after deployment

Run this on the mounted export from the app pod:

```sh
kubectl -n cet-time exec deployment/cet-time -- python storage_check.py
```

The check creates and removes a separate temporary SQLite database beside the app DB. It tests a write, DELETE journaling, contention between two local processes, and quick_check. It never opens or modifies the live tracker database. A pass is not proof of cross-node locking correctness, crash recovery, or durable server sync behavior. The actual NFS export cannot be verified by the authoring environment; test in your cluster before using student records.

## Activate Trello

1. Open your HTTP PUBLIC_URL and log in as `admin` using `cet-time-admin-password`.
2. Connections → Load boards → choose your board → map the four lists → activate tracking.
3. Register the signed HTTP webhook only if Trello Cloud can reach the callback at `PUBLIC_URL/webhook` and receive HTTP 200 for HEAD validation. A private internal-only URL cannot receive Trello Cloud webhooks; use instructor **Refresh & sync** during the pilot. The server also reconciles history every five minutes while running; inspect tracking health before final reporting.
4. Create individual student logins and test the working → paused → working → completed workflow.

HTTP login traffic is unencrypted. Keep this on a trusted internal network with test accounts/data. In-app break reminders work; browser notifications and the one-click Clipboard API need HTTPS in normal browser deployments. Select and manually copy the report's clipboard preview during the HTTP pilot. Trello permits reachable HTTP callbacks but rejects invalid HTTPS certificates: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/ .

## Updates and backups

The app uses **one replica**, Recreate deployment strategy, a per-process lock around all DB sessions, DELETE rollback journaling, synchronous FULL, and a 30-second SQLite busy timeout. Each context-managed DB session closes its connection. Recreate briefly interrupts the portal during rollout; instructor Refresh & sync recovers Trello history afterward. There is no automatic rollback or PV/PVC deletion. The server creates verified, rotating database snapshots every six hours by default.

Use the instructor Backups screen for verified snapshots and downloads, or stop the app before copying the entire app data directory. Automatic snapshots default to `/app/data/backups` on the existing persistent mount; `BACKUP_INTERVAL_HOURS=6` and `BACKUP_KEEP=28` are included in the ConfigMap. Keep an independent copy outside the NFS export. See README for the offline restore procedure. Do not copy only a live database file while a journal transaction is running. Keep separate backup copies outside this export. If migrating existing records from a previous mount, stop the old app, preserve its full data, and copy the DB into `/srv/nfs/roseaw/cet-time/` with the correct ownership before starting this deployment.

Changing the initial admin-password Jenkins secret does not reset an existing account. Deployment rollback changes the workload only, not persistent data, Secrets, or ConfigMaps. Keep this pilot at one running instance.

