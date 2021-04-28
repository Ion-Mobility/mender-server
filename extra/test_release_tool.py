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

import os
import sys
import shutil
import re
import pathlib
from unittest.mock import patch

import pytest

from release_tool import main
from release_tool import docker_compose_files_list
from release_tool import Component

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
RELEASE_TOOL = os.path.join(THIS_DIR, "release_tool.py")
INTEGRATION_DIR = os.path.normpath(os.path.join(THIS_DIR, ".."))


@pytest.fixture(scope="function", autouse=True)
def master_yml_files(request):
    """Edit all yml files setting them to 'master'/'mender-master' versions

    So that the tests can be run from any branch or with any
    local changes in the yml files. The files are restored after
    the test run.
    """

    docker_files = docker_compose_files_list(INTEGRATION_DIR, "docker")
    for filename in docker_files:
        shutil.copyfile(filename, filename + ".bkp")
    for filename in docker_compose_files_list(INTEGRATION_DIR, "git"):
        if filename not in docker_files:
            shutil.copyfile(filename, filename + ".bkp")

    for filename in docker_files:
        with open(filename) as fd:
            full_content = "".join(fd.readlines())
        with open(filename, "w") as fd:
            fd.write(
                re.sub(
                    r"image:\s+(mendersoftware|.*mender\.io)/((?!mender\-client\-.+|mender-artifact|mender-cli).+):.*",
                    r"image: \g<1>/\g<2>:mender-master",
                    full_content,
                )
            )
        with open(filename) as fd:
            full_content = "".join(fd.readlines())
        with open(filename, "w") as fd:
            fd.write(
                re.sub(
                    r"image:\s+(mendersoftware|.*mender\.io)/(mender\-client\-.+|mender-artifact|mender-cli):.*",
                    r"image: \g<1>/\g<2>:master",
                    full_content,
                )
            )

    for filename in docker_compose_files_list(INTEGRATION_DIR, "git"):
        if filename not in docker_files:
            with open(filename) as fd:
                full_content = "".join(fd.readlines())
            with open(filename, "w") as fd:
                fd.write(
                    re.sub(
                        r"image:\s+(mendersoftware|.*mender\.io)/(.+):.*",
                        r"image: \g<1>/\g<2>:master",
                        full_content,
                    )
                )

    def restore():
        docker_files = docker_compose_files_list(INTEGRATION_DIR, "docker")
        for filename in docker_files:
            os.rename(filename + ".bkp", filename)
        for filename in docker_compose_files_list(INTEGRATION_DIR, "git"):
            if filename not in docker_files:
                os.rename(filename + ".bkp", filename)

    request.addfinalizer(restore)


def run_main_assert_result(capsys, args, expect=None):
    testargs = [RELEASE_TOOL] + args
    with patch.object(sys, "argv", testargs):
        main()

    captured = capsys.readouterr().out.strip()
    if expect is not None:
        assert captured == expect
    return captured


def test_version_of(capsys):
    # On a clean checkout, both will be master
    run_main_assert_result(capsys, ["--version-of", "deviceauth"], "master")
    run_main_assert_result(
        capsys,
        ["--version-of", "deviceauth", "--version-type", "docker"],
        "mender-master",
    )
    run_main_assert_result(
        capsys, ["--version-of", "deviceauth", "--version-type", "git"], "master"
    )

    # For an independent component, it should still accept docker/git type of the query
    run_main_assert_result(capsys, ["--version-of", "mender"], "master")
    run_main_assert_result(
        capsys, ["--version-of", "mender", "--version-type", "docker"], "master"
    )
    run_main_assert_result(
        capsys, ["--version-of", "mender", "--version-type", "git"], "master"
    )
    run_main_assert_result(capsys, ["--version-of", "mender-client-qemu"], "master")
    run_main_assert_result(
        capsys,
        ["--version-of", "mender-client-qemu", "--version-type", "docker"],
        "master",
    )
    run_main_assert_result(
        capsys,
        ["--version-of", "mender-client-qemu", "--version-type", "git"],
        "master",
    )

    # Manually modifying the Git version:
    filename = os.path.join(INTEGRATION_DIR, "git-versions.yml")
    with open(filename, "w") as fd:
        fd.write(
            """services:
    mender-deviceauth:
        image: mendersoftware/deviceauth:1.2.3-git
"""
        )
    run_main_assert_result(capsys, ["--version-of", "deviceauth"], "1.2.3-git")
    run_main_assert_result(
        capsys,
        ["--version-of", "deviceauth", "--version-type", "docker"],
        "mender-master",
    )
    run_main_assert_result(
        capsys, ["--version-of", "deviceauth", "--version-type", "git"], "1.2.3-git"
    )

    # Manually modifying the Docker version:
    filename = os.path.join(INTEGRATION_DIR, "docker-compose.yml")
    with open(filename, "w") as fd:
        fd.write(
            """services:
    mender-deviceauth:
        image: mendersoftware/deviceauth:4.5.6-docker
"""
        )
    run_main_assert_result(capsys, ["--version-of", "deviceauth"], "1.2.3-git")
    run_main_assert_result(
        capsys,
        ["--version-of", "deviceauth", "--version-type", "docker"],
        "4.5.6-docker",
    )
    run_main_assert_result(
        capsys, ["--version-of", "deviceauth", "--version-type", "git"], "1.2.3-git"
    )


def test_version_of_with_in_integration_version(capsys):
    # In remote master, shall be master
    run_main_assert_result(
        capsys,
        ["--version-of", "inventory", "--in-integration-version", "master"],
        "master",
    )
    run_main_assert_result(
        capsys,
        [
            "--version-of",
            "inventory",
            "--version-type",
            "docker",
            "--in-integration-version",
            "master",
        ],
        "mender-master",
    )
    run_main_assert_result(
        capsys,
        [
            "--version-of",
            "inventory",
            "--version-type",
            "git",
            "--in-integration-version",
            "master",
        ],
        "master",
    )

    # For old releases, --version-type shall be ignored
    run_main_assert_result(
        capsys,
        ["--version-of", "inventory", "--in-integration-version", "2.3.0"],
        "1.7.0",
    )
    run_main_assert_result(
        capsys,
        [
            "--version-of",
            "inventory",
            "--version-type",
            "git",
            "--in-integration-version",
            "2.3.0",
        ],
        "1.7.0",
    )
    run_main_assert_result(
        capsys,
        [
            "--version-of",
            "inventory",
            "--version-type",
            "docker",
            "--in-integration-version",
            "2.3.0",
        ],
        "1.7.0",
    )


def test_set_version_of(capsys):
    # Using --set-version-of modifies both versions, regardless of using the repo name
    run_main_assert_result(
        capsys, ["--set-version-of", "deviceauth", "--version", "1.2.3-test"]
    )
    run_main_assert_result(capsys, ["--version-of", "deviceauth"], "1.2.3-test")
    run_main_assert_result(
        capsys, ["--version-of", "deviceauth", "--version-type", "docker"], "1.2.3-test"
    )
    run_main_assert_result(
        capsys, ["--version-of", "deviceauth", "--version-type", "git"], "1.2.3-test"
    )

    # or the container name. However, setting from the container name sets all repos (os + ent)
    run_main_assert_result(
        capsys, ["--set-version-of", "mender-deployments", "--version", "4.5.6-test"]
    )
    run_main_assert_result(capsys, ["--version-of", "mender-deployments"], "4.5.6-test")
    run_main_assert_result(
        capsys,
        ["--version-of", "mender-deployments", "--version-type", "docker"],
        "4.5.6-test",
    )
    run_main_assert_result(
        capsys,
        ["--version-of", "mender-deployments", "--version-type", "git"],
        "4.5.6-test",
    )
    # NOTE: skip check for OS flavor for branches without it (namely staging)
    list_repos = run_main_assert_result(capsys, ["--list", "git"], None)
    if "deployments" in list_repos.split("\n"):
        run_main_assert_result(capsys, ["--version-of", "deployments"], "4.5.6-test")
        run_main_assert_result(
            capsys,
            ["--version-of", "deployments", "--version-type", "docker"],
            "4.5.6-test",
        )
        run_main_assert_result(
            capsys,
            ["--version-of", "deployments", "--version-type", "git"],
            "4.5.6-test",
        )
    run_main_assert_result(
        capsys, ["--version-of", "deployments-enterprise"], "4.5.6-test"
    )
    run_main_assert_result(
        capsys,
        ["--version-of", "deployments-enterprise", "--version-type", "docker"],
        "4.5.6-test",
    )
    run_main_assert_result(
        capsys,
        ["--version-of", "deployments-enterprise", "--version-type", "git"],
        "4.5.6-test",
    )


def test_integration_versions_including(capsys):
    captured = run_main_assert_result(
        capsys,
        ["--integration-versions-including", "inventory", "--version", "master"],
        None,
    )
    # The output shall be <remote>/master
    assert captured.endswith("/master")

    captured = run_main_assert_result(
        capsys,
        ["--integration-versions-including", "inventory", "--version", "1.6.x"],
        None,
    )
    # Three versions: <remote>/2.2.x, <remote>/2.1.x, <remote>/2.0.x
    versions = captured.split("\n")
    assert len(versions) == 3
    assert versions[0].endswith("/2.2.x")
    assert versions[1].endswith("/2.1.x")
    assert versions[2].endswith("/2.0.x")


def test_docker_compose_files_list():
    list_git = docker_compose_files_list(INTEGRATION_DIR, version="git")
    list_git_filenames = [os.path.basename(file) for file in list_git]
    assert "docker-compose.client.demo.yml" in list_git_filenames
    assert "docker-compose.no-ssl.yml" in list_git_filenames
    assert "docker-compose.testing.enterprise.yml" in list_git_filenames
    assert "other-components.yml" in list_git_filenames
    assert "docker-compose.storage.minio.yml" in list_git_filenames
    assert "docker-compose.client.rofs.yml" in list_git_filenames
    assert "docker-compose.client-dev.yml" in list_git_filenames
    assert "docker-compose.mt.client.yml" in list_git_filenames
    assert "docker-compose.demo.yml" in list_git_filenames
    assert "docker-compose.client.yml" in list_git_filenames
    assert "docker-compose.docker-client.yml" in list_git_filenames

    assert "git-versions.yml" in list_git_filenames
    assert "git-versions-enterprise.yml" in list_git_filenames
    assert "docker-compose.yml" not in list_git_filenames
    assert "docker-compose.enterprise.yml" not in list_git_filenames

    list_docker = docker_compose_files_list(INTEGRATION_DIR, version="docker")
    list_docker_filenames = [os.path.basename(file) for file in list_docker]
    assert "docker-compose.client.demo.yml" in list_docker_filenames
    assert "docker-compose.no-ssl.yml" in list_docker_filenames
    assert "docker-compose.testing.enterprise.yml" in list_docker_filenames
    assert "other-components.yml" in list_docker_filenames
    assert "docker-compose.storage.minio.yml" in list_docker_filenames
    assert "docker-compose.client.rofs.yml" in list_docker_filenames
    assert "docker-compose.client-dev.yml" in list_docker_filenames
    assert "docker-compose.mt.client.yml" in list_docker_filenames
    assert "docker-compose.demo.yml" in list_docker_filenames
    assert "docker-compose.client.yml" in list_docker_filenames
    assert "docker-compose.docker-client.yml" in list_docker_filenames

    assert "git-versions.yml" not in list_docker_filenames
    assert "git-versions-enterprise.yml" not in list_docker_filenames
    assert "docker-compose.yml" in list_docker_filenames
    assert "docker-compose.enterprise.yml" in list_docker_filenames


@patch("release_tool.integration_dir")
def test_get_components_of_type(integration_dir_func):
    integration_dir_func.return_value = pathlib.Path(__file__).parent.parent.absolute()

    # standard query (only_release=None)
    repos_comp = Component.get_components_of_type("git")
    repos_name = [r.name for r in repos_comp]
    assert "deployments" in repos_name
    assert "deployments-enterprise" in repos_name
    assert "deviceauth" in repos_name
    assert "gui" in repos_name
    assert "integration" in repos_name
    assert "inventory" in repos_name
    assert "inventory-enterprise" in repos_name
    assert "mender" in repos_name
    assert "mender-artifact" in repos_name
    assert "mender-cli" in repos_name
    assert "tenantadm" in repos_name
    assert "useradm" in repos_name
    assert "useradm-enterprise" in repos_name
    assert "workflows" in repos_name
    assert "workflows-enterprise" in repos_name
    assert "create-artifact-worker" in repos_name
    assert "auditlogs" in repos_name
    assert "mtls-ambassador" in repos_name
    assert "deviceconnect" in repos_name
    assert "mender-connect" in repos_name
    assert "deviceconfig" in repos_name

    # only_release=False
    repos_comp = Component.get_components_of_type("git", only_release=False)
    repos_name = [r.name for r in repos_comp]
    assert "deployments" in repos_name
    assert "deployments-enterprise" in repos_name
    assert "deviceauth" in repos_name
    assert "gui" in repos_name
    assert "integration" in repos_name
    assert "inventory" in repos_name
    assert "inventory-enterprise" in repos_name
    assert "mender" in repos_name
    assert "mender-artifact" in repos_name
    assert "mender-cli" in repos_name
    assert "tenantadm" in repos_name
    assert "useradm" in repos_name
    assert "useradm-enterprise" in repos_name
    assert "workflows" in repos_name
    assert "workflows-enterprise" in repos_name
    assert "create-artifact-worker" in repos_name
    assert "auditlogs" in repos_name
    assert "mtls-ambassador" in repos_name
    assert "deviceconnect" in repos_name
    assert "mender-connect" in repos_name
    assert "deviceconfig" in repos_name
    # should also include deprecated repos
    assert "deviceadm" in repos_name
    assert "mender-api-gateway-docker" in repos_name
    assert "mender-conductor" in repos_name
    assert "mender-conductor-enterprise" in repos_name

    # only_non_release=True
    repos_comp = Component.get_components_of_type("git", only_non_release=True)
    repos_name = [r.name for r in repos_comp]
    assert "deployments" not in repos_name
    assert "deployments-enterprise" not in repos_name
    assert "deviceauth" not in repos_name
    assert "gui" not in repos_name
    assert "integration" not in repos_name
    assert "inventory" not in repos_name
    assert "inventory-enterprise" not in repos_name
    assert "mender" not in repos_name
    assert "mender-artifact" not in repos_name
    assert "mender-cli" not in repos_name
    assert "tenantadm" not in repos_name
    assert "useradm" not in repos_name
    assert "useradm-enterprise" not in repos_name
    assert "workflows" not in repos_name
    assert "workflows-enterprise" not in repos_name
    assert "create-artifact-worker" not in repos_name
    assert "auditlogs" not in repos_name
    assert "mtls-ambassador" not in repos_name
    assert "deviceconnect" not in repos_name
    assert "mender-connect" not in repos_name
    assert "deviceconfig" not in repos_name
    # should only include deprecated repos
    assert "deviceadm" in repos_name
    assert "mender-api-gateway-docker" in repos_name
    assert "mender-conductor" in repos_name
    assert "mender-conductor-enterprise" in repos_name

    # only_independent_component=True
    repos_comp = Component.get_components_of_type(
        "git", only_independent_component=True
    )
    repos_name = [r.name for r in repos_comp]
    assert "deployments" not in repos_name
    assert "deployments-enterprise" not in repos_name
    assert "deviceauth" not in repos_name
    assert "gui" not in repos_name
    assert "inventory" not in repos_name
    assert "inventory-enterprise" not in repos_name
    assert "tenantadm" not in repos_name
    assert "useradm" not in repos_name
    assert "useradm-enterprise" not in repos_name
    assert "workflows" not in repos_name
    assert "workflows-enterprise" not in repos_name
    assert "create-artifact-worker" not in repos_name
    assert "auditlogs" not in repos_name
    assert "mtls-ambassador" not in repos_name
    assert "deviceconnect" not in repos_name
    assert "deviceconfig" not in repos_name
    # should only include non backend repos
    assert "integration" in repos_name
    assert "mender" in repos_name
    assert "mender-artifact" in repos_name
    assert "mender-cli" in repos_name
    assert "mender-connect" in repos_name

    # only_non_independent_component=True
    repos_comp = Component.get_components_of_type(
        "git", only_non_independent_component=True
    )
    repos_name = [r.name for r in repos_comp]
    assert "integration" not in repos_name
    assert "mender" not in repos_name
    assert "mender-artifact" not in repos_name
    assert "mender-cli" not in repos_name
    assert "mender-connect" not in repos_name
    # should only include backend repos
    assert "deployments" in repos_name
    assert "deployments-enterprise" in repos_name
    assert "deviceauth" in repos_name
    assert "gui" in repos_name
    assert "inventory" in repos_name
    assert "inventory-enterprise" in repos_name
    assert "tenantadm" in repos_name
    assert "useradm" in repos_name
    assert "useradm-enterprise" in repos_name
    assert "workflows" in repos_name
    assert "workflows-enterprise" in repos_name
    assert "create-artifact-worker" in repos_name
    assert "auditlogs" in repos_name
    assert "mtls-ambassador" in repos_name
    assert "deviceconnect" in repos_name
    assert "deviceconfig" in repos_name


def test_list_repos(capsys):
    run_main_assert_result(
        capsys,
        ["--list"],
        """auditlogs
create-artifact-worker
deployments
deployments-enterprise
deviceauth
deviceconfig
deviceconnect
gui
integration
inventory
inventory-enterprise
mender
mender-artifact
mender-cli
mender-connect
mtls-ambassador
tenantadm
useradm
useradm-enterprise
workflows
workflows-enterprise""",
    )

    run_main_assert_result(
        capsys,
        ["--list", "--only-backend"],
        """auditlogs
create-artifact-worker
deployments
deployments-enterprise
deviceauth
deviceconfig
deviceconnect
gui
inventory
inventory-enterprise
mtls-ambassador
tenantadm
useradm
useradm-enterprise
workflows
workflows-enterprise""",
    )
