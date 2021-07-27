# Copyright 2021 Northern.tech AS
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import urllib3
import pytest
import subprocess
import time

from urllib.parse import urlparse

# See https://docs.pytest.org/en/latest/writing_plugins.html#assertion-rewriting
pytest.register_assert_rewrite("testutils")

from requests.packages import urllib3
from testutils.common import wait_until_healthy
from testutils.infra.container_manager.kubernetes_manager import isK8S

urllib3.disable_warnings()

wait_until_healthy("backend-tests")


forward_port = 8080


@pytest.fixture(scope="session")
def get_endpoint_url():
    processes = {}

    def _get_endpoint_url(url):
        global forward_port
        if isK8S() and url.startswith("http://mender-"):
            url_parsed = urlparse(url)
            host = url_parsed.hostname
            port = url_parsed.port
            _, host_forward_port = processes.get(host, (None, None))
            if host_forward_port is None:
                forward_port += 1
                host_forward_port = forward_port
                cmd = [
                    "kubectl",
                    "port-forward",
                    "service/" + host,
                    "%d:%d" % (host_forward_port, port),
                ]
                p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL)
                processes[host] = (p, host_forward_port)
                # wait a few seconds to let the port-forwarding fully initialize
                time.sleep(3)
            url = ("http://localhost:%d" % host_forward_port) + url_parsed.path
        return url

    try:
        yield _get_endpoint_url
    finally:
        for p, _ in processes.values():
            p.terminate()
