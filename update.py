import pkg_resources
from subprocess import call

packages = [dist.project_name for dist in pkg_resources.working_set]
for i in range(0, len(packages), 1):
    call("python -m pip install --upgrade " + packages[i], shell=True)