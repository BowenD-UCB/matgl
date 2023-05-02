from __future__ import annotations

import os
from pathlib import Path

import requests

from matgl.config import PRETRAINED_MODELS_PATH


class ModelSource:
    """
    Defines a local or remote source for models.
    """

    def __init__(self, uri: str, use_cache: bool = True, force_download: bool = False):
        """

        Args:
            uri: Uniform resource identifier.
            use_cache: By default, downloaded models are saved at $HOME/.matgl/models. If False, models will be
                downloaded to current working directory.
            force_download: To speed up access, a model with the same name in the cache location will be used if
                present. If you want to force a re-download, set this to True.
        """
        self.uri = uri
        self.model_name = uri.split("/")[-1]
        if use_cache:
            if not PRETRAINED_MODELS_PATH.exists():
                os.makedirs(PRETRAINED_MODELS_PATH)
            self.local_path = PRETRAINED_MODELS_PATH / self.model_name
        else:
            self.local_path = Path(self.model_name)
        if (not self.local_path.exists()) or force_download:
            self._download()

    def _download(self):
        r = requests.get(self.uri, allow_redirects=True)
        with open(self.local_path, "wb") as f:
            f.write(r.content)

    def __enter__(self):
        """
        Support with context.

        Returns:
            Stream on local path.
        """
        self.stream = open(self.local_path, "rb")
        return self.stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the with context.

        Args:
            exc_type:
            exc_val:
            exc_tb:

        Returns:

        """
        self.stream.close()