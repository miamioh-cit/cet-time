pipeline {
    agent any
    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 25, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }
    parameters {
        string(name: 'IMAGE_REPOSITORY', defaultValue: '', description: 'Full repository without tag, e.g. docker.io/YOUR_ORG/cet-time')
        string(name: 'REGISTRY_HOST', defaultValue: 'docker.io', description: 'Registry login host, matching IMAGE_REPOSITORY')
        string(name: 'REGISTRY_CREDENTIAL_ID', defaultValue: '', description: 'Jenkins Username with password credential for registry push')
        string(name: 'KUBECONFIG_CREDENTIAL_ID', defaultValue: 'cet-time', description: 'Jenkins Secret file credential containing kubeconfig')
        string(name: 'KUBE_NAMESPACE', defaultValue: 'cet-time', description: 'Existing Kubernetes namespace')
        string(name: 'PUBLIC_URL', defaultValue: '', description: 'Exact app origin, e.g. https://time.example.edu; HTTP requires ALLOW_HTTP')
        booleanParam(name: 'ALLOW_HTTP', defaultValue: false, description: 'Allow unencrypted HTTP for an internal pilot without a certificate; browser notifications require HTTPS')
        booleanParam(name: 'ENABLE_INGRESS', defaultValue: true, description: 'Create an Ingress for PUBLIC_URL; otherwise use your existing reverse proxy')
        string(name: 'INGRESS_CLASS', defaultValue: '', description: 'Ingress class; blank uses cluster default')
        string(name: 'TLS_SECRET_NAME', defaultValue: '', description: 'Existing TLS Secret in the namespace (required only for HTTPS Ingress)')
        string(name: 'STORAGE_CLASS', defaultValue: '', description: 'Block-backed storage class; blank uses cluster default. Do not use NFS for SQLite.')
        string(name: 'STORAGE_SIZE', defaultValue: '5Gi', description: 'PVC request at initial creation; do not shrink existing claims')
        string(name: 'IMAGE_PULL_SECRET', defaultValue: '', description: 'Existing registry pull Secret in namespace, if needed')
    }
    environment {
        PYTHONDONTWRITEBYTECODE = '1'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Validate and test') {
            steps {
                script {
                    if (!params.REGISTRY_CREDENTIAL_ID?.trim()) { error('Set REGISTRY_CREDENTIAL_ID to your registry credential ID.') }
                    env.IMAGE_TAG = "build-${env.BUILD_NUMBER}-${sh(script: 'git rev-parse --short=12 HEAD', returnStdout: true).trim()}"
                    env.IMAGE_REF = "${params.IMAGE_REPOSITORY}:${env.IMAGE_TAG}"
                }
                sh '''
                    set -eu
                    python3 -m unittest -v
                    python3 deploy/render.py --output .deploy-check.json
                    docker version >/dev/null
                    kubectl version --client >/dev/null
                '''
            }
        }
        stage('Build image') {
            steps { sh 'docker build --pull --tag "$IMAGE_REF" .' }
        }
        stage('Push image') {
            steps {
                withCredentials([usernamePassword(credentialsId: params.REGISTRY_CREDENTIAL_ID,
                                                   usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD')]) {
                    sh '''
                        set +x
                        set -eu
                        DOCKER_CONFIG=$(mktemp -d)
                        export DOCKER_CONFIG
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT HUP INT TERM
                        printf '%s' "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" --username "$REGISTRY_USER" --password-stdin
                        docker push "$IMAGE_REF"
                        python3 deploy/resolve_digest.py > .image-digest
                    '''
                }
            }
        }
        stage('Deploy to Kubernetes') {
            steps {
                withCredentials([
                    file(credentialsId: params.KUBECONFIG_CREDENTIAL_ID, variable: 'KUBECONFIG'),
                    string(credentialsId: 'cet-time-admin-password', variable: 'ADMIN_PASSWORD'),
                    string(credentialsId: 'cet-time-trello-key', variable: 'TRELLO_KEY'),
                    string(credentialsId: 'cet-time-trello-token', variable: 'TRELLO_TOKEN'),
                    string(credentialsId: 'cet-time-trello-secret', variable: 'TRELLO_SECRET')
                ]) {
                    sh '''
                        set +x
                        set -eu
                        # No namespace creation: cet-time may be scoped to a pre-created namespace.
                        kubectl -n "$KUBE_NAMESPACE" get deployments >/dev/null
                        IMAGE_REF=$(cat .image-digest)
                        export IMAGE_REF
                        python3 deploy/render.py --output .deployment.json
                        # Validate against this cluster before changing workloads or secrets.
                        kubectl apply --dry-run=server -f .deployment.json >/dev/null
                        python3 deploy/apply_secret.py
                        kubectl apply -f .deployment.json
                        kubectl -n "$KUBE_NAMESPACE" rollout status deployment/cet-time --timeout=300s
                        kubectl -n "$KUBE_NAMESPACE" get deployment/cet-time service/cet-time pvc/cet-time-data
                    '''
                }
            }
        }
    }
    post {
        success { echo "Deployed cet-time to ${params.KUBE_NAMESPACE}. Open ${params.PUBLIC_URL} to configure the Trello board." }
        failure { echo 'Build/deployment failed. Check the failed stage. Existing time data is retained on cet-time-data; no automatic rollback or PVC deletion is performed.' }
        always {
            archiveArtifacts artifacts: '.deployment.json,.image-digest', allowEmptyArchive: true
            sh 'rm -f .deploy-check.json .deployment.json .image-digest'
        }
    }
}
