import os,shutil,subprocess
from pathlib import Path
import pytest


def test_deployment_success_stale_and_rollback(tmp_path):
    bash=shutil.which("bash")
    if os.name=="nt":
        bash=r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).exists():
        pytest.fail("Bash required for deployment regression tests")
    root=Path(__file__).resolve().parents[1]
    def path(p):
        text=str(p).replace("\\","/")
        if os.name=="nt":text="/"+text[0].lower()+text[2:]
        return text
    result=subprocess.run([bash,path(root/"tests/test_deploy.sh"),path(tmp_path),path(root/"ci/deploy.sh")],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert "rollback tests passed" in result.stdout
