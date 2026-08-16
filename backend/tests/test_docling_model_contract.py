from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "docker" / "docling-sidecar" / "requirements.txt"
ENTRYPOINT = ROOT / "docker" / "docling-sidecar" / "entrypoint.sh"


def test_docling_runtime_is_pinned_to_current_release_and_standard_bundle() -> None:
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "docling==2.117.0" in requirements
    assert 'DOCLING_EXPECTED_VERSION="${DOCLING_EXPECTED_VERSION:-2.117.0}"' in entrypoint
    assert "docling-${DOCLING_EXPECTED_VERSION}-standard-default" in entrypoint
    assert "docling-tools models download -o \"$staging_dir\"" in entrypoint
    assert 'HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"' in entrypoint


def test_docling_model_cache_cannot_skip_without_matching_manifest() -> None:
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert 'grep -Fxq "${MODEL_BUNDLE_ID}" "$MODEL_MANIFEST"' in entrypoint
    assert 'find "$ARTIFACTS_DIR" -type f' in entrypoint
    assert 'staging_dir="${ARTIFACTS_DIR}.staging.$$"' in entrypoint


def test_docling_gpu_install_uses_resilient_pip_download_settings() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.gpu").read_text(encoding="utf-8")

    docling_stage = dockerfile.split("FROM filex-os-base-gpu AS filex-docling-base-gpu", 1)[1]
    assert "--timeout 600" in docling_stage
    assert "--retries 10" in docling_stage
