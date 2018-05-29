# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import json
import os
import uuid
import tempfile
import logging
import webbrowser
import shutil

from knack.util import CLIError

from vsts.cli.common.exception_handling import handle_command_exception
from vsts.cli.common.identities import resolve_identity_as_display_name
from vsts.cli.common.services import get_upack_client, resolve_instance
from vsts.cli.common.uri import uri_quote
from vsts.exceptions import VstsServiceError

from .artifacttool import ArtifactToolInvoker, ArtifactToolUpdater

logger = logging.getLogger('vsts.packaging')

def publish_package(team_instance, feed, name, version, path, description=None):
    """Publish a package to a feed
    :param team_instance: VSTS account URL. Example: https://myaccount.visualstudio.com
    :type team_instance: str
    :param feed: Name or ID of the feed
    :type feed: str
    :param name: Name of the package, e.g. 'my-cool-package'
    :type name: str
    :param version: Version of the package, e.g. 1.0.0
    :type version: str
    :param description: Description of the package
    :type description: str
    :param path: Directory containing the package contents
    :type path: str
    """
    try:
        artifact_tool = ArtifactToolInvoker(ArtifactToolUpdater())
        artifact_tool.publish_upack(team_instance, feed, name, version, description, path)
    except Exception as ex:
        handle_command_exception(ex)
      
def download_package(team_instance, feed, name, version, path):
    """Download a package
    :param team_instance: VSTS account URL. Example: https://myaccount.visualstudio.com
    :type team_instance: str
    :param feed: Name or ID of the feed
    :type feed: str
    :param name: Name of the package, e.g. 'my-cool-package'
    :type name: str
    :param version: Version of the package, e.g. 1.0.0
    :type version: str
    :param path: Directory to place the package contents
    :type path: str
    """
    try:
        artifact_tool = ArtifactToolInvoker(ArtifactToolUpdater())
        artifact_tool.download_upack(team_instance, feed, name, version, path)
    except Exception as ex:
        handle_command_exception(ex)