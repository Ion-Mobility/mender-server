# Copyright 2022 Northern.tech AS
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

import json
import pytest
import uuid

from . import conftest

from .MenderAPI import authentication, auth, devauth, reset_mender_api, DeviceAuthV2

from testutils.common import User, new_tenant_client
from testutils.infra.cli import CliTenantadm
from testutils.infra.device import MenderDevice, MenderDeviceGroup
from testutils.infra.container_manager import factory

container_factory = factory.get_factory()


@pytest.fixture(scope="function")
def standard_setup_one_client(request):
    env = container_factory.getStandardSetup(num_clients=1)
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)

    env.auth = auth
    return env


@pytest.fixture(scope="function")
def monitor_commercial_setup_no_client(request):
    env = container_factory.getMonitorCommercialSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    return env


def standard_setup_one_client_bootstrapped_impl(request):
    env = container_factory.getStandardSetup(num_clients=1)
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    devauth.accept_devices(1)

    env.auth = auth
    return env


@pytest.fixture(scope="function")
def standard_setup_one_client_bootstrapped(request):
    return standard_setup_one_client_bootstrapped_impl(request)


@pytest.fixture(scope="class")
def class_persistent_standard_setup_one_client_bootstrapped(request):
    return standard_setup_one_client_bootstrapped_impl(request)


@pytest.fixture(scope="function")
def standard_setup_one_rofs_client_bootstrapped(request):
    env = container_factory.getRofsClientSetup()
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    devauth.accept_devices(1)

    env.auth = auth
    return env


@pytest.fixture(scope="function")
def standard_setup_one_docker_client_bootstrapped(request):
    env = container_factory.getDockerClientSetup()
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    devauth.accept_devices(1)

    env.auth = auth
    return env


@pytest.fixture(scope="function")
def standard_setup_two_clients_bootstrapped(request):
    env = container_factory.getStandardSetup(num_clients=2)
    request.addfinalizer(env.teardown)

    env.setup()

    env.device_group = MenderDeviceGroup(env.get_mender_clients())
    env.device_group.ssh_is_opened()

    reset_mender_api(env)
    devauth.accept_devices(2)

    env.auth = auth
    return env


@pytest.fixture(scope="function")
def standard_setup_without_client(request):
    env = container_factory.getStandardSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    return env


@pytest.fixture(scope="function")
def setup_with_legacy_client(request):
    # The legacy 1.7.0 client was only built for qemux86-64, so skip tests using
    # it when running other platforms.
    if conftest.machine_name != "qemux86-64":
        pytest.skip(
            "Test only works with qemux86-64, and this is %s" % conftest.machine_name
        )

    env = container_factory.getLegacyClientSetup()
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    devauth.accept_devices(1)

    return env


@pytest.fixture(scope="function")
def standard_setup_with_signed_artifact_client(request):
    env = container_factory.getSignedArtifactClientSetup()
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    auth.reset_auth_token()
    devauth.accept_devices(1)

    return env


@pytest.fixture(scope="function")
def standard_setup_with_short_lived_token(request):
    env = container_factory.getShortLivedTokenSetup()
    request.addfinalizer(env.teardown)

    env.setup()

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    reset_mender_api(env)
    auth.reset_auth_token()
    devauth.accept_devices(1)

    return env


@pytest.fixture(scope="function")
def setup_failover(request):
    env = container_factory.getFailoverServerSetup()
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    env.device = MenderDevice(env.get_mender_clients()[0])
    env.device.ssh_is_opened()

    auth.reset_auth_token()
    devauth.accept_devices(1)

    return env


@pytest.fixture(scope="function")
def running_custom_production_setup(request):
    conftest.production_setup_lock.acquire()

    env = container_factory.getCustomSetup()

    def fin():
        env.teardown()
        conftest.production_setup_lock.release()

    request.addfinalizer(fin)

    reset_mender_api(env)

    return env


@pytest.fixture(scope="function")
def enterprise_no_client(request):
    env = container_factory.getEnterpriseSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    return env


@pytest.fixture(scope="function")
def enterprise_one_client(request):
    env = container_factory.getEnterpriseSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    uuidv4 = str(uuid.uuid4())
    tname = "test.mender.io-{}".format(uuidv4)
    email = "some.user+{}@example.com".format(uuidv4)
    u = User("", email, "whatsupdoc")
    cli = CliTenantadm(containers_namespace=env.name)
    tid = cli.create_org(tname, u.name, u.pwd, plan="os")

    tenant = cli.get_tenant(tid)
    tenant = json.loads(tenant)
    env.tenant = tenant

    auth = authentication.Authentication(
        name="os-tenant", username=u.name, password=u.pwd
    )
    auth.create_org = False
    auth.reset_auth_token()
    env.auth = auth

    mender_device = new_tenant_client(env, "test-container", tenant["tenant_token"])
    mender_device.ssh_is_opened()
    env.device = mender_device

    return env


@pytest.fixture(scope="function")
def enterprise_one_client_bootstrapped(request):
    env = container_factory.getEnterpriseSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    uuidv4 = str(uuid.uuid4())
    tname = "test.mender.io-{}".format(uuidv4)
    email = "some.user+{}@example.com".format(uuidv4)
    u = User("", email, "whatsupdoc")
    cli = CliTenantadm(containers_namespace=env.name)
    tid = cli.create_org(tname, u.name, u.pwd, plan="os")

    tenant = cli.get_tenant(tid)
    tenant = json.loads(tenant)
    env.tenant = tenant

    auth = authentication.Authentication(
        name="os-tenant", username=u.name, password=u.pwd
    )
    auth.create_org = False
    auth.reset_auth_token()
    env.auth = auth

    mender_device = new_tenant_client(env, "test-container", tenant["tenant_token"])
    mender_device.ssh_is_opened()
    env.device = mender_device

    devauth_tenant = DeviceAuthV2(auth)
    devauth_tenant.accept_devices(1)
    devices = devauth_tenant.get_devices_status("accepted")
    assert 1 == len(devices)

    return env


@pytest.fixture(scope="function")
def enterprise_two_clients_bootstrapped(request):
    env = container_factory.getEnterpriseSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    uuidv4 = str(uuid.uuid4())
    tname = "test.mender.io-{}".format(uuidv4)
    email = "some.user+{}@example.com".format(uuidv4)
    u = User("", email, "whatsupdoc")
    cli = CliTenantadm(containers_namespace=env.name)
    tid = cli.create_org(tname, u.name, u.pwd, plan="os")

    tenant = cli.get_tenant(tid)
    tenant = json.loads(tenant)
    env.tenant = tenant

    auth = authentication.Authentication(
        name="os-tenant", username=u.name, password=u.pwd
    )
    auth.create_org = False
    auth.reset_auth_token()
    env.auth = auth

    new_tenant_client(env, "test-container-1", tenant["tenant_token"])
    new_tenant_client(env, "test-container-2", tenant["tenant_token"])
    env.device_group.ssh_is_opened()

    devauth_tenant = DeviceAuthV2(auth)
    devauth_tenant.accept_devices(2)
    devices = devauth_tenant.get_devices_status("accepted", expected_devices=2)
    assert 2 == len(devices)

    return env


@pytest.fixture(scope="class")
def enterprise_no_client_class(request):
    env = container_factory.getEnterpriseSetup(num_clients=0)
    request.addfinalizer(env.teardown)

    env.setup()
    reset_mender_api(env)

    return env
