# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from setuptools import setup, find_packages
from pathlib import Path

setup(
    name="notebook_nanoservice",
    version="0.1.2",
    packages=find_packages(where="."),
    author="Your Name",
    author_email="danmar@microsoft@example.com",
    description="Nanoservices for notebooks",
    long_description=Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/microsoft/notebook-nanoservice"
)
