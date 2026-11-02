$ErrorActionPreference = 'Stop'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "External command failed with exit $LASTEXITCODE" } }
$tip = git ls-remote origin refs/heads/main
Check-Exit
if (($tip -split "\s+")[0] -ne $env:RELEASE_SHA) { throw 'Refusing stale release: main has advanced' }
# Jenkins credential files inherit workspace ACLs; OpenSSH requires a private ACL.
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$keyAcl = New-Object System.Security.AccessControl.FileSecurity
$keyAcl.SetOwner($identity)
$keyAcl.SetAccessRuleProtection($true, $false)
$keyAcl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')))
Set-Acl -LiteralPath $env:SSH_KEY -AclObject $keyAcl
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
