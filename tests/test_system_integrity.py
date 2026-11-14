"""
MARSCOPE System Integrity & Architecture Verification Tests
"""

import os
from pathlib import Path


def test_core_master_documents_exist():
    root = Path(__file__).parent.parent
    assert (root / "plan.md").is_file(), "plan.md master document must exist"
    assert (root / "DATA_SOURCES.md").is_file(), "DATA_SOURCES.md register must exist"
    assert (root / "README.md").is_file(), "README.md must exist"
    assert (root / "LICENSE").is_file(), "LICENSE must exist"
    assert (root / ".env.example").is_file(), ".env.example must exist"
    assert (root / ".gitignore").is_file(), ".gitignore must exist"


def test_documentation_suite_exists():
    root = Path(__file__).parent.parent / "docs"
    expected_docs = [
        "architecture.md",
        "data-policy.md",
        "scientific-methodology.md",
        "physics-models.md",
        "api-contracts.md",
        "validation-plan.md",
        "demo-script.md",
    ]
    for doc in expected_docs:
        doc_path = root / doc
        assert doc_path.is_file(), f"Documentation file {doc} must exist"
        assert doc_path.stat().st_size > 100, f"Documentation file {doc} must not be empty"


def test_dataset_directories_exist():
    root = Path(__file__).parent.parent / "datasets"
    expected_subdirs = ["catalog", "raw", "processed", "manifests"]
    for subdir in expected_subdirs:
        dir_path = root / subdir
        assert dir_path.is_dir(), f"Dataset directory {subdir} must exist"


def test_backend_subsystems_exist():
    app_dir = Path(__file__).parent.parent / "backend" / "app"
    subsystems = [
        "api",
        "ingestion",
        "geospatial",
        "terrain",
        "science",
        "physics",
        "routing",
        "mission",
        "schemas",
        "services",
    ]
    for sub in subsystems:
        assert (app_dir / sub).is_dir(), f"Backend subsystem app/{sub} must exist"
        assert (app_dir / sub / "__init__.py").is_file(), f"Backend subsystem app/{sub}/__init__.py must exist"

    physics_dir = app_dir / "physics"
    physics_subsystems = ["registry", "units", "models", "uncertainty"]
    for psub in physics_subsystems:
        assert (physics_dir / psub).is_dir(), f"Physics submodule physics/{psub} must exist"
        assert (physics_dir / psub / "__init__.py").is_file(), f"Physics submodule physics/{psub}/__init__.py must exist"
