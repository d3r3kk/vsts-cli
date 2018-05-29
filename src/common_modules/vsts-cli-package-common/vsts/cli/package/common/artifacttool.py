# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import json
import logging
import os
import platform
import signal
import sys
import tempfile
import zipfile
import pathlib

import requests
import io
import zipfile

from knack.util import CLIError
from vsts.cli.common.services import _get_credentials
from .external_tool import ProgressReportingExternalToolInvoker

logger = logging.getLogger('vsts.packaging')

class ArtifactToolUpdater:
    ARTIFACTTOOL_OVERRIDE_PATH_ENVKEY = "VSTS_ARTIFACTTOOL_OVERRIDE_PATH"
    ARTIFACTTOOL_OVERRIDE_URL_ENVKEY = "VSTS_ARTIFACTTOOL_OVERRIDE_URL"
    DEFAULT_ARTIFACTTOOL_BINARY_URL = "https://zachtest1.blob.core.windows.net/test/artifacttool-win10-x64-Release.zip"

    def get_latest_artifacttool(self, team_instance):
        artifacttool_binary_override_path = os.environ.get(self.ARTIFACTTOOL_OVERRIDE_PATH_ENVKEY)
        if artifacttool_binary_override_path is not None:
            artifacttool_binary_path = artifacttool_binary_override_path
            logger.debug("ArtifactTool path was overriden to '%s' due to environment variable %s" % (artifacttool_binary_path, self.ARTIFACTTOOL_OVERRIDE_PATH_ENVKEY))
        else:
            logger.debug("Checking for a new ArtifactTool")
            artifacttool_binary_path = self._update_artifacttool(team_instance)
            logger.debug("Using downloaded ArtifactTool from '%s'" % artifacttool_binary_path)
        return artifacttool_binary_path

    def _update_artifacttool(self, team_instance):
        logger.debug("Checking for ArtifactTool updates")
        artifacttool_binary_url = self.DEFAULT_ARTIFACTTOOL_BINARY_URL
        artifacttool_binary_override_url = os.environ.get(self.ARTIFACTTOOL_OVERRIDE_URL_ENVKEY)
        if artifacttool_binary_override_url is not None:
            artifacttool_binary_url = artifacttool_binary_override_url
            logger.debug("ArtifactTool download URL was overridden to '%s' due to environment variable %s" % (artifacttool_binary_override_url, self.ARTIFACTTOOL_OVERRIDE_URL_ENVKEY))
        else:
            logger.debug("Using default update URL '%s'" % artifacttool_binary_url)

        head_result = requests.head(artifacttool_binary_url)
        etag = head_result.headers.get('ETag').strip("\"").replace("0x", "").lower()
        logger.debug("Latest ArtifactTool is ETag '%s'" % etag)

        temp_dir = tempfile.gettempdir()
        tool_root = os.path.join(temp_dir, "ArtifactTool")
        tool_dir = os.path.join(tool_root, etag)
          
        # For now, just download if the directory for this etag doesn't exist
        binary_path = os.path.join(tool_dir, "artifacttool-win10-x64-Release", "ArtifactTool.exe")
        if os.path.exists(binary_path):
            logger.debug("Not downloading ArtifactTool as it already exists at %s" % tool_dir)
        else:
            logger.debug("Downloading ArtifactTool to %s" % tool_dir)
            content = requests.get(artifacttool_binary_url)
            f = zipfile.ZipFile(io.BytesIO(content.content))
            f.extractall(path=tool_dir)

        return binary_path

class ArtifactToolInvoker(ProgressReportingExternalToolInvoker):
    def __init__(self, artifacttool_updater):
        self._artifacttool_updater = artifacttool_updater
        super().__init__()

    PATVAR = "VSTS_ARTIFACTTOOL_PATVAR"

    def download_upack(self, team_instance, feed, package_name, package_version, path):
        self.invoke_artifacttool(team_instance, ["upack", "download", "--service", team_instance, "--patvar", self.PATVAR, "--feed", feed, "--package-name", package_name, "--package-version", package_version, "--path", path], "Downloading")

    def publish_upack(self, team_instance, feed, package_name, package_version, description, path):
        args = ["upack", "publish", "--service", team_instance, "--patvar", self.PATVAR, "--feed", feed, "--package-name", package_name, "--package-version", package_version, "--path", path]
        if description:
            args.extend(["--description", description])
        self.invoke_artifacttool(team_instance, args, "Publishing")

    def invoke_artifacttool(self, team_instance, args, initial_progress_message):
        # Download ArtifactTool if necessary, and return the path
        artifacttool_path = self._artifacttool_updater.get_latest_artifacttool(team_instance)

        # Populate the environment for the process with the PAT
        creds = _get_credentials(team_instance)
        new_env = os.environ.copy()
        new_env[self.PATVAR] = creds.password

        # Run ArtifactTool
        command_args = [artifacttool_path] + args

        self.run(command_args, new_env, initial_progress_message, self._process_stderr)

    def _process_stderr(self, line, update_progress_callback):
        try:
            json_line = json.loads(line)
        except:
            json_line = None
            logger.debug("Failed to parse JSON log line. Ensure that ArtifactTool structured logging is enabled.")

        if json_line is not None and '@m' in json_line:
            log_level = json_line['@l'] if '@l' in json_line else "Information" # Serilog doesn't emit @l for Information it seems
            message = json_line['@m']
            if log_level in ["Critical", "Error"]:
                ex = json_line['@x'] if '@x' in json_line else None
                if ex:
                    message = "%s\n%s" % (message, ex)
                raise CLIError(message)
            elif log_level == "Warning":
                logger.warning(message)
            elif log_level == "Information":
                logger.info(message)
            else:
                logger.debug(message)
        else:          
            logger.debug(line)

        if json_line and 'EventId' in json_line and 'Name' in json_line['EventId']:
            event_name = json_line['EventId']['Name']

            if event_name == "ProcessingFiles":
                processed_files = json_line['ProcessedFiles']
                total_files = json_line['TotalFiles']
                percent = 100 * float(processed_files) / float(total_files)
                update_progress_callback("Pre-upload processing: %s/%s files" % (processed_files, total_files), percent)

            if event_name == "Uploading":
                uploaded_bytes = json_line['UploadedBytes']
                total_bytes = json_line['TotalBytes']
                percent = 100 * float(uploaded_bytes) / float(total_bytes)
                update_progress_callback("Uploading: %s/%s bytes" % (uploaded_bytes, total_bytes), percent)

            if event_name == "Downloading":
                downloaded_bytes = json_line['DownloadedBytes']
                total_bytes = json_line['TotalBytes']
                percent = 100 * float(downloaded_bytes) / float(total_bytes)
                update_progress_callback("Downloading: %s/%s bytes" % (downloaded_bytes, total_bytes), percent)

