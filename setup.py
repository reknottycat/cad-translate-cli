#!/usr/bin/env python3
from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent

with (ROOT / "README.md").open("r", encoding="utf-8") as fh:
    long_description = fh.read()

install_requires = [
    "click>=8.1.0",
    "prompt-toolkit>=3.0.0",
    "rich>=13.7.0",
    "ezdxf>=1.3.0",
    "pandas>=2.2.0",
    "openpyxl>=3.1.0",
    "requests>=2.31.0",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "structlog>=24.1.0",
    "python-dotenv>=1.0.1",
    "psutil>=5.9.0",
    "pywin32>=306; platform_system == 'Windows'",
]

setup(
    name="cad-translate-cli",
    version="1.0.1",
    author="cad-translate contributors",
    description="CAD图纸翻译CLI工具 - DWG/DXF文字提取、LLM翻译、回填",
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "cad-translate=cli.cad_cli:main",
        ],
    },
    packages=find_packages(include=["cli", "cli.*", "lib", "lib.*"]),
    zip_safe=False,
)
