"""Setup configuration for LEGO label generator."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="lego-labels",
    version="0.1.0",
    author="LEGO Label Generator",
    description="A CLI tool for generating printable LEGO part labels",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ayhid/brick-labels",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "beautifulsoup4>=4.11.0",
        "reportlab>=3.6.0",
        "Pillow>=9.0.0",
        "click>=8.0.0",
    ],
    extras_require={
        # --print only. niimprint itself is not on PyPI and pins Python 3.11,
        # so it is installed separately from git with --no-deps (see README).
        "print": ["pyserial>=3.5"],
        "dev": ["pytest"],
    },
    entry_points={
        "console_scripts": [
            "lego-labels=lego_labels.cli:main",
        ],
    },
)
