def deploymentSettings = []

pipeline {
    agent any
    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 25, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }
    environment {
        PYTHONDONTWRITEBYTECODE = '1'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Load deployment settings') {
            steps {
                script {
                    // Literal KEY=value entries; no extra Jenkins parsing plugin or shell sourcing.
                    deploymentSettings = sh(
                        script: 'python3 deploy/settings.py', returnStdout: true
                    ).trim().split('\n').toList()
                    echo 'Loaded non-secret deployment settings from deploy/jenkins.json.'
                }
            }
        }
        stage('Validate and test') {
            steps {
                script {
                    withEnv(deploymentSettings) {
                        env.IMAGE_TAG = "build-${env.BUILD_NUMBER}-${sh(script: 'git rev-parse --short=12 HEAD', returnStdout: true).trim()}"
                        env.IMAGE_REF = "${env.IMAGE_REPOSITORY}:${env.IMAGE_TAG}"
                        sh '''
                            set -eu
                            python3 -m unittest -v
                            python3 deploy/render.py --output .deploy-check.json
                            docker version >/dev/null
                            kubectl version --client >/dev/null
                        '''
                    }
                }
            }
        }
        stage('Build image') {
            steps {
                script {
                    withEnv(deploymentSettings) {
                        sh 'docker build --pull --tag "$IMAGE_REF" .'
                    }
                }
            }
        }
        stage('Push image') {
            steps {
                script {
                    withEnv(deploymentSettings) {
                        withCredentials([usernamePassword(credentialsId: env.REGISTRY_CREDENTIAL_ID,
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
            }
        }
        stage('Deploy to Kubernetes') {
            steps {
                script {
                    withEnv(deploymentSettings) {
                        withCredentials([
                            file(credentialsId: env.KUBECONFIG_CREDENTIAL_ID, variable: 'KUBECONFIG'),
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
                        echo "Deployed cet-time to ${env.KUBE_NAMESPACE}. Open ${env.PUBLIC_URL} to configure the Trello board."
                    }
                }
            }
        }
    }
    post {
        failure { echo 'Build/deployment failed. Check the failed stage. Existing time data is retained on cet-time-data; no automatic rollback or PVC deletion is performed.' }
        always {
            archiveArtifacts artifacts: '.deployment.json,.image-digest', allowEmptyArchive: true
            sh 'rm -f .deploy-check.json .deployment.json .image-digest'
        }
    }
}

