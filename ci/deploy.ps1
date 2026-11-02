$ErrorActionPreference = 'Stop'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "External command failed with exit $LASTEXITCODE" } }
$tip = git ls-remote origin refs/heads/main
Check-Exit
if (($tip -split "\s+")[0] -ne $env:RELEASE_SHA) { throw 'Refusing stale release: main has advanced' }
$target = "$($env:SSH_USER)@$($env:AZURE_HOST)"
$incoming = "$($env:DEPLOY_ROOT)/.ci/incoming/$($env:BUILD_NUMBER)-$($env:RELEASE_SHA)"
$options = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$PSScriptRoot/known_hosts",'-i',$env:SSH_KEY)
& ssh @options $target "mkdir -p '$incoming'"
Check-Exit
& scp @options release.tar "${target}:$incoming/release.tar"
Check-Exit
& scp @options "$PSScriptRoot/deploy.sh" "${target}:$incoming/deploy.sh"
Check-Exit
& ssh @options $target "bash '$incoming/deploy.sh' '$env:RELEASE_SHA' '$env:BUILD_NUMBER' '$env:DEPLOY_ROOT'"
Check-Exit
