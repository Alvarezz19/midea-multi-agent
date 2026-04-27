from __future__ import annotations

import re
import subprocess
import sys
import unittest
from importlib.metadata import PackageNotFoundError, version


VERIFIED_MIN_VERSIONS = {
    "langgraph": "1.0.6",
    "langchain": "1.2.6",
    "chromadb": "1.4.1",
    "langchain-openai": "1.1.7",
    "openai": "2.15.0",
    "pydantic": "2.12.4",
    "sentence-transformers": "5.2.0",
    "torch": "2.10.0",
    "transformers": "4.57.6",
    "python-dotenv": "1.2.1",
    "langsmith": "0.6.0",
}


def _version_key(raw_version: str) -> tuple[int, ...]:
    numbers = [int(part) for part in re.findall(r"\d+", raw_version)]
    return tuple(numbers[:4])


class RuntimeVersionTests(unittest.TestCase):
    def test_installed_runtime_meets_verified_min_versions(self) -> None:
        missing_packages: list[str] = []
        mismatched_versions: list[str] = []

        for package_name, minimum_version in VERIFIED_MIN_VERSIONS.items():
            try:
                installed_version = version(package_name)
            except PackageNotFoundError:
                missing_packages.append(package_name)
                continue

            if _version_key(installed_version) < _version_key(minimum_version):
                mismatched_versions.append(
                    f"{package_name}: installed={installed_version}, expected>={minimum_version}"
                )

        if missing_packages or mismatched_versions:
            message_lines = []
            if missing_packages:
                message_lines.append("missing: " + ", ".join(sorted(missing_packages)))
            if mismatched_versions:
                message_lines.extend(mismatched_versions)
            self.fail("\n".join(message_lines))

    def test_pip_check_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            check=False,
        )
        details = "\n".join(filter(None, [completed.stdout.strip(), completed.stderr.strip()]))
        self.assertEqual(completed.returncode, 0, details or "pip check failed")


if __name__ == "__main__":
    unittest.main()
