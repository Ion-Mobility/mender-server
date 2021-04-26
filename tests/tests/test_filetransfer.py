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
#

import json
import io
import os
import os.path
import random
import requests
import shutil
import tempfile
import pytest
import time
import urllib.parse

from tempfile import NamedTemporaryFile

from ..common_setup import standard_setup_one_client, enterprise_no_client

from ..MenderAPI import (
    authentication,
    devauth,
    get_container_manager,
    reset_mender_api,
    DeviceAuthV2,
    logger,
)
from .common_connect import wait_for_connect
from .common import md5sum
from .mendertesting import MenderTesting
from testutils.infra.container_manager import factory
from testutils.infra.device import MenderDevice
from testutils.common import Tenant, User, update_tenant
from testutils.infra.cli import CliTenantadm

container_factory = factory.get_factory()
connect_service_name = "mender-connect"


def download_file(path, devid, authtoken):
    deviceconnect_url = (
        "https://%s/api/management/v1/deviceconnect"
        % get_container_manager().get_mender_gateway()
    )
    download_url = "%s/devices/%s/download" % (deviceconnect_url, devid)
    download_url_with_path = download_url + "?path=" + urllib.parse.quote(path)
    return requests.get(download_url_with_path, verify=False, headers=authtoken)


def upload_file(path, file, devid, authtoken, mode="600", uid="0", gid="0"):
    files = (
        ("path", (None, path)),
        ("mode", (None, mode)),
        ("uid", (None, uid)),
        ("gid", (None, gid)),
        ("file", (os.path.basename(path), file, "application/octet-stream"),),
    )
    deviceconnect_url = (
        "https://%s/api/management/v1/deviceconnect"
        % get_container_manager().get_mender_gateway()
    )
    upload_url = "%s/devices/%s/upload" % (deviceconnect_url, devid)
    return requests.put(upload_url, verify=False, headers=authtoken, files=files)


def set_limits(mender_device, limits, auth, devid):
    tmpdir = tempfile.mkdtemp()
    try:
        # retrieve the original configuration file
        output = mender_device.run("cat /etc/mender/mender-connect.conf")
        config = json.loads(output)
        # update mender-connect.conf setting the file transfer limits
        config["Limits"] = limits
        mender_connect_conf = os.path.join(tmpdir, "mender-connect.conf")
        with open(mender_connect_conf, "w") as fd:
            json.dump(config, fd)
        mender_device.run(
            "cp /etc/mender/mender-connect.conf /etc/mender/mender-connect.conf-backup-`ls /etc/mender/mender-connect.* | wc -l`"
        )
        mender_device.put(
            os.path.basename(mender_connect_conf),
            local_path=os.path.dirname(mender_connect_conf),
            remote_path="/etc/mender",
        )
    finally:
        shutil.rmtree(tmpdir)
    mender_device.run("systemctl restart %s" % connect_service_name)
    wait_for_connect(auth, devid)
    debugoutput = mender_device.run("cat /etc/mender/mender-connect.conf")
    logger.info("/etc/mender/mender-connect.conf:\n%s" % debugoutput)
    debugoutput = mender_device.run("ls -al /etc/mender")
    logger.info("ls -al /etc/mender/:\n%s" % debugoutput)


class _TestFileTransferBase(MenderTesting):
    def test_filetransfer(
        self, devid, authtoken, path="/etc/mender/mender.conf", content_assertion=None
    ):
        # download a file and check its content
        r = download_file(path, devid, authtoken)

        assert r.status_code == 200, r.json()
        if content_assertion:
            assert content_assertion in str(r.content)
        assert (
            r.headers.get("Content-Disposition")
            == 'attachment; filename="' + os.path.basename(path) + '"'
        )
        assert r.headers.get("Content-Type") == "application/octet-stream"
        assert r.headers.get("X-Men-File-Gid") == "0"
        assert r.headers.get("X-Men-File-Uid") == "0"
        assert r.headers.get("X-Men-File-Mode") == "600"
        assert r.headers.get("X-Men-File-Path") == "/etc/mender/mender.conf"
        assert r.headers.get("X-Men-File-Size") != ""

        # wrong request, path is relative
        path = "relative/path"
        r = download_file(path, devid, authtoken)
        assert r.status_code == 400, r.json()
        assert r.json().get("error") == "bad request: path: must be absolute."

        # wrong request, no such file or directory
        path = "/does/not/exist"
        r = download_file(path, devid, authtoken)
        assert r.status_code == 400, r.json()
        assert "/does/not/exist: no such file or directory" in r.json().get("error")

        try:
            # create a 40MB random file
            f = NamedTemporaryFile(delete=False)
            for i in range(40 * 1024):
                f.write(os.urandom(1024))
            f.close()

            # random uid and gid
            uid = random.randint(100, 200)
            gid = random.randint(100, 200)

            # upload the file
            r = upload_file(
                "/tmp/random.bin",
                open(f.name, "rb"),
                devid,
                authtoken,
                mode="600",
                uid=str(uid),
                gid=str(gid),
            )
            assert r.status_code == 201, r.json()

            # download the file
            path = "/tmp/random.bin"
            r = download_file(path, devid, authtoken)
            assert r.status_code == 200, r.json()
            assert (
                r.headers.get("Content-Disposition")
                == 'attachment; filename="random.bin"'
            )
            assert r.headers.get("Content-Type") == "application/octet-stream"
            assert r.headers.get("X-Men-File-Mode") == "600"
            assert r.headers.get("X-Men-File-Uid") == str(uid)
            assert r.headers.get("X-Men-File-Gid") == str(gid)
            assert r.headers.get("X-Men-File-Path") == "/tmp/random.bin"
            assert r.headers.get("X-Men-File-Size") == str(40 * 1024 * 1024)

            filename_download = f.name + ".download"
            with open(filename_download, "wb") as fw:
                fw.write(r.content)

            # verify the file is not corrupted
            assert md5sum(filename_download) == md5sum(f.name)
        finally:
            os.unlink(f.name)
            if os.path.isfile(f.name + ".download"):
                os.unlink(f.name + ".download")

        # wrong request, path is relative
        r = upload_file(
            "relative/path/dummy.txt",
            io.StringIO("dummy"),
            devid,
            authtoken,
            mode="600",
            uid="0",
            gid="0",
        )
        assert r.status_code == 400, r.json()
        assert r.json().get("error") == "bad request: path: must be absolute."

        # wrong request, cannot write the file
        r = upload_file(
            "/does/not/exist/dummy.txt",
            io.StringIO("dummy"),
            devid,
            authtoken,
            mode="600",
            uid="0",
            gid="0",
        )
        assert r.status_code == 400, r.json()
        assert "failed to create target file" in r.json().get("error")


class TestFileTransfer(_TestFileTransferBase):
    """Tests the file transfer functionality"""

    def test_filetransfer(self, standard_setup_one_client):
        """Tests the file transfer features"""
        # accept the device
        devauth.accept_devices(1)

        # list of devices
        devices = list(
            set([device["id"] for device in devauth.get_devices_status("accepted")])
        )
        assert 1 == len(devices)

        # wait for the device to connect via websocket
        auth = authentication.Authentication()
        wait_for_connect(auth, devices[0])

        # device ID and auth token
        devid = devices[0]
        authtoken = auth.get_auth_token()

        super().test_filetransfer(devid, authtoken, content_assertion="ServerURL")

    @pytest.fixture(scope="function")
    def setup_mender_connect_1_0(self, request):
        self.env = container_factory.getMenderClient_2_5()
        request.addfinalizer(self.env.teardown)
        self.env.setup()

        self.env.populate_clients(replicas=1)

        clients = self.env.get_mender_clients()
        assert len(clients) == 1, "Failed to setup client"
        self.env.device = MenderDevice(clients[0])
        self.env.device.ssh_is_opened()

        reset_mender_api(self.env)

        yield self.env

    def test_filetransfer_not_implemented(self, setup_mender_connect_1_0):
        # accept the device
        devauth.accept_devices(1)

        auth = authentication.Authentication()
        authtoken = auth.get_auth_token()

        # list of devices
        devices = list(
            set([device["id"] for device in devauth.get_devices_status("accepted")])
        )
        assert 1 == len(devices)
        devid = devices[0]

        wait_for_connect(auth, devid)

        rsp = upload_file("/foo/bar", io.StringIO("foobar"), devid, authtoken)
        assert rsp.status_code == 502
        rsp = download_file("/foo/bar", devid, authtoken)
        assert rsp.status_code == 502


class TestFileTransferEnterprise(_TestFileTransferBase):
    def test_filetransfer(self, enterprise_no_client):
        u = User("", "bugs.bunny@acme.org", "whatsupdoc")
        cli = CliTenantadm(containers_namespace=enterprise_no_client.name)
        tid = cli.create_org("os-tenant", u.name, u.pwd, plan="os")

        # FT requires "troubleshoot"
        update_tenant(
            tid, addons=["troubleshoot"], container_manager=get_container_manager(),
        )

        tenant = cli.get_tenant(tid)
        tenant = json.loads(tenant)

        auth = authentication.Authentication(
            name="os-tenant", username=u.name, password=u.pwd
        )
        auth.create_org = False
        auth.reset_auth_token()
        devauth_tenant = DeviceAuthV2(auth)

        enterprise_no_client.new_tenant_client(
            "configuration-test-container", tenant["tenant_token"]
        )
        mender_device = MenderDevice(enterprise_no_client.get_mender_clients()[0])
        mender_device.ssh_is_opened()

        devauth_tenant.accept_devices(1)

        devices = list(
            set(
                [
                    device["id"]
                    for device in devauth_tenant.get_devices_status("accepted")
                ]
            )
        )
        assert 1 == len(devices)

        wait_for_connect(auth, devices[0])

        authtoken = auth.get_auth_token()

        super().test_filetransfer(devices[0], authtoken, content_assertion="ServerURL")


class TestFileTransferLimits:
    def setup_test_filetransfer_limits(self, standard_setup_one_client):
        """Tests the file transfer features"""
        # accept the device
        devauth.accept_devices(1)

        # list of devices
        devices = list(
            set([device["id"] for device in devauth.get_devices_status("accepted")])
        )
        assert 1 == len(devices)

        # wait for the device to connect via websocket
        auth = authentication.Authentication()
        wait_for_connect(auth, devices[0])

        # device ID and auth token
        devid = devices[0]
        authtoken = auth.get_auth_token()

        mender_device = MenderDevice(standard_setup_one_client.get_mender_clients()[0])
        mender_device.ssh_is_opened()
        return mender_device, devid, auth

    def test_filetransfer_limits_upload(self, standard_setup_one_client):
        mender_device, devid, auth = self.setup_test_filetransfer_limits(
            standard_setup_one_client
        )
        authtoken = auth.get_auth_token()
        """Tests the file transfer features with limits"""
        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {"Chroot": "/var/lib/mender/filetransfer"},
            },
            auth,
            devid,
        )
        mender_device.run("mkdir -p /var/lib/mender/filetransfer")

        logger.info(
            "-- testcase: File Transfer limits: file outside chroot; upload forbidden"
        )
        f = NamedTemporaryFile(delete=False)
        for i in range(40 * 1024):
            f.write(os.urandom(1024))
        f.close()
        r = upload_file("/usr/random.bin", open(f.name, "rb"), devid, authtoken,)

        assert r.status_code == 400, r.json()
        assert (
            r.json().get("error")
            == "access denied: the target file path is outside chroot"
        )

        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {
                    "Chroot": "/var/lib/mender/filetransfer",
                    "FollowSymLinks": True,  # in the image /var/lib/mender is a symlink
                },
            },
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file inside chroot; upload allowed"
        )
        f = NamedTemporaryFile(delete=False)
        f.write(os.urandom(16))
        f.close()
        # upload a file
        r = upload_file(
            "/var/lib/mender/filetransfer/random.bin",
            open(f.name, "rb"),
            devid,
            authtoken,
        )

        assert r.status_code == 201

        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {"MaxFileSize": 16378, "FollowSymLinks": True},
            },
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file size over the limit; upload forbidden"
        )
        f = NamedTemporaryFile(delete=False)
        for i in range(128 * 1024):
            f.write(b"ok")
        f.close()
        r = upload_file("/tmp/random.bin", open(f.name, "rb"), devid, authtoken,)

        assert r.status_code == 400, r.json()
        assert (
            r.json().get("error")
            == "failed to write file chunk: transmitted bytes limit exhausted"
        )

        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {
                    "FollowSymLinks": True,
                    "Counters": {"MaxBytesRxPerMinute": 16784},
                },
            },
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: transfers during last minute over the limit; upload forbidden"
        )
        f = NamedTemporaryFile(delete=False)
        for i in range(128 * 1024):
            f.write(b"ok")
        f.close()
        upload_file(
            "/tmp/random-0.bin", open(f.name, "rb"), devid, authtoken,
        )
        upload_file(
            "/tmp/random-1.bin", open(f.name, "rb"), devid, authtoken,
        )
        logger.info("-- testcase: File Transfer limits: sleeping to gather the avg")

        time.sleep(32)  # wait for mender-connect to calculate the 1m exp moving avg
        mender_device.run(
            "kill -USR1 `pidof mender-connect`"
        )  # USR1 makes mender-connect print status

        r = upload_file("/tmp/random-2.bin", open(f.name, "rb"), devid, authtoken,)

        assert r.status_code == 400, r.json()
        assert r.json().get("error") == "transmitted bytes limit exhausted"

        logger.info(
            "-- testcase: File Transfer limits: transfers during last minute: test_filetransfer_limits_upload sleeping 64s to be able to transfer again"
        )
        # let's rest some more and increase the limit and try again
        time.sleep(64)
        mender_device.run(
            "kill -USR1 `pidof mender-connect`"
        )  # USR1 makes mender-connect print status

        logger.info(
            "-- testcase: File Transfer limits: transfers during last minute below the limit; upload allowed"
        )
        f = NamedTemporaryFile(delete=False)
        for i in range(64):
            f.write(b"ok")
        f.close()
        # upload a file
        r = upload_file("/tmp/random-a.bin", open(f.name, "rb"), devid, authtoken,)
        mender_device.run(
            "kill -USR1 `pidof mender-connect`"
        )  # USR1 makes mender-connect print status

        assert r.status_code == 201

        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {
                    "Chroot": "/var/lib/mender/filetransfer",
                    "FollowSymLinks": True,  # in the image /var/lib/mender is a symlink
                    "PreserveMode": True,
                },
            },
            auth,
            devid,
        )

        logger.info("-- testcase: File Transfer limits: preserve modes;")
        f = NamedTemporaryFile(delete=False)
        f.write(os.urandom(16))
        f.close()
        r = upload_file(
            "/var/lib/mender/filetransfer/modes.bin",
            open(f.name, "rb"),
            devid,
            authtoken,
            mode="4711",
        )
        modes_ls = mender_device.run("ls -al /var/lib/mender/filetransfer/modes.bin")
        logger.info(
            "test_filetransfer_limits_upload ls -al /var/lib/mender/filetransfer/modes.bin:\n%s"
            % modes_ls
        )

        assert modes_ls.startswith("-rws--x--x")
        assert r.status_code == 201

        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {
                    "Chroot": "/var/lib/mender/filetransfer",
                    "FollowSymLinks": True,  # in the image /var/lib/mender is a symlink
                    "PreserveOwner": True,
                    "PreserveGroup": True,
                },
            },
            auth,
            devid,
        )

        logger.info("-- testcase: File Transfer limits: preserve owner and group;")
        f = NamedTemporaryFile(delete=False)
        f.write(os.urandom(16))
        f.close()
        gid = int(mender_device.run("cat /etc/group | tail -1| cut -f3 -d:"))
        uid = int(mender_device.run("cat /etc/passwd | tail -1| cut -f3 -d:"))
        logger.info("test_filetransfer_limits_upload gid/uid %d/%d", gid, uid)
        r = upload_file(
            "/var/lib/mender/filetransfer/ownergroup.bin",
            open(f.name, "rb"),
            devid,
            authtoken,
            uid=str(uid),
            gid=str(gid),
        )
        owner_group = mender_device.run(
            "ls -aln /var/lib/mender/filetransfer/ownergroup.bin | cut -f 3,4 -d' '"
        )

        assert owner_group == str(uid) + " " + str(gid) + "\n"
        assert r.status_code == 201

    def test_filetransfer_limits_download(self, standard_setup_one_client):
        mender_device, devid, auth = self.setup_test_filetransfer_limits(
            standard_setup_one_client
        )
        authtoken = auth.get_auth_token()
        """Tests the file transfer features with limits"""
        set_limits(
            mender_device,
            {
                "Enabled": True,
                "FileTransfer": {"Chroot": "/var/lib/mender/filetransfer"},
            },
            auth,
            devid,
        )

        path = "/etc/profile"
        r = download_file(path, devid, authtoken)

        logger.info(
            "-- testcase: File Transfer limits: file outside chroot; download forbidden"
        )

        assert r.status_code == 500, r.json()
        assert (
            r.json().get("error")
            == "access denied: the target file path is outside chroot"
        )

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"MaxFileSize": 2}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file over the max file size limit; download forbidden"
        )

        path = "/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 500, r.json()
        assert r.json().get("error") == "access denied: the file size is over the limit"

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"FollowSymLinks": False}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: not allowed to follow a link; download forbidden"
        )

        path = "/tmp/profile-link"
        mender_device.run("ln -s /etc/profile " + path)
        r = download_file(path, devid, authtoken)

        assert r.status_code == 500, r.json()
        assert r.json().get("error") == "access denied: forbidden to follow the link"

        logger.info(
            "-- testcase: File Transfer limits: not allowed to follow a link on path part; download forbidden"
        )

        mender_device.run("cd /tmp && mkdir level0 && cd level0 && ln -s /etc")
        # now we have a link to the etc directory under /tmp/level0/etc
        path = "/tmp/level0/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 500, r.json()
        assert r.json().get("error") == "access denied: forbidden to follow the link"

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"FollowSymLinks": True}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: not allowed to follow a link; download forbidden"
        )

        path = "/tmp/profile-link"
        # mender_device.run("ln -s /etc/profile " + path) # present already after the previous test case
        # download a file and check its content
        r = download_file(path, devid, authtoken)

        assert r.status_code == 200, r.json()
        assert "PATH" in str(r.content)

        logger.info(
            "-- testcase: File Transfer limits: not allowed to follow a link on path part; download forbidden"
        )

        # we have a link to the etc directory under /tmp/level0/etc from the previous run
        path = "/tmp/level0/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 200, r.json()
        assert "PATH" in str(r.content)

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"OwnerGet": ["someotheruser"]}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file owner do not match; download forbidden"
        )

        path = "/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 500, r.json()
        assert r.json().get("error") == "access denied: the file owner does not match"

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"GroupGet": ["someothergroup"]}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file group do not match; download forbidden"
        )

        path = "/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 500, r.json()
        assert r.json().get("error") == "access denied: the file group does not match"

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"RegularFilesOnly": True}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file owner do not match; download forbidden"
        )

        path = "/tmp/f0.fifo"
        mender_device.run("mkfifo " + path)
        r = download_file(path, devid, authtoken)

        assert r.status_code == 400, r.json()
        assert (
            r.json().get("error") == "file transfer failed: path is not a regular file"
        )

        set_limits(
            mender_device,
            {"Enabled": True, "FileTransfer": {"OwnerGet": ["someotheruser", "root"]}},
            auth,
            devid,
        )

        logger.info(
            "-- testcase: File Transfer limits: file owner match; download allowed"
        )

        path = "/etc/profile"
        r = download_file(path, devid, authtoken)

        assert r.status_code == 200, r.json()
        assert "PATH" in str(r.content)
