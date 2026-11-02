pipeline {
    agent any
    options { disableConcurrentBuilds(); timestamps(); timeout(time: 45, unit: 'MINUTES'); buildDiscarder(logRotator(numToKeepStr: '20')) }
    triggers { pollSCM('H/2 * * * *') }
    parameters { booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Deploy after successful tests') }
    environment {
        PYTHON = 'C:\\ProgramData\\Jenkins\\tools\\Python312\\tools\\python.exe'
        PYTHONUTF8 = '1'
        AZURE_HOST = '172.197.160.37'
        DEPLOY_ROOT = '/home/azureuser/expense-tracker'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm; script { env.RELEASE_SHA = bat(returnStdout: true, script: '@git rev-parse HEAD').trim() } }
        }
        stage('Dependencies') {
            steps { bat '"%PYTHON%" -m venv --clear .ci-venv'; bat '.ci-venv\\Scripts\\python.exe -m pip install --disable-pip-version-check -r requirements-dev.txt'; bat '.ci-venv\\Scripts\\python.exe -m pip check' }
        }
        stage('Test') {
            steps { bat '.ci-venv\\Scripts\\python.exe -m pytest -q --junitxml=test-results/pytest.xml' }
            post { always { junit 'test-results/pytest.xml' } }
        }
        stage('Package') {
            steps { bat 'git archive --format=tar -o release.tar %RELEASE_SHA%'; archiveArtifacts artifacts: 'release.tar', fingerprint: true }
        }
        stage('Deploy Azure') {
            when { expression { params.DEPLOY } }
            steps {
                withCredentials([sshUserPrivateKey(credentialsId: 'expense-azure-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
                    powershell(script: 'ci/deploy.ps1')
                }
            }
        }
    }
    post { success { echo "Verified commit ${env.RELEASE_SHA}; deploy=${params.DEPLOY}" }; failure { echo 'Tests or deployment failed; inspect stage output. Deployment failures restore the previous release.' } }
}
