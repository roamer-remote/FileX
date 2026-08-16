variable "REGISTRY" {
  default = "ghcr.io/roamer-remote"
}

variable "SOURCE_TAG" {
  default = "dev"
}

group "core-versioned" {
  targets = [
    "app-versioned",
    "kb-extract-versioned",
    "postgres-versioned",
  ]
}

group "core-stable" {
  targets = [
    "app-stable",
    "kb-extract-stable",
    "postgres-stable",
  ]
}

target "_platforms" {
  context   = "."
  platforms = ["linux/amd64", "linux/arm64"]
}

target "_published" {
  inherits = ["_platforms"]
  attest   = ["type=provenance,mode=min"]
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/roamer-remote/filex"
    "org.opencontainers.image.revision" = SOURCE_TAG
    "org.opencontainers.image.vendor"   = "FileX"
  }
  output = ["type=registry"]
}

target "os-base" {
  inherits   = ["_platforms"]
  dockerfile = "docker/Dockerfile.base"
  target     = "filex-os-base"
  args = {
    PYTHON_IMAGE = "docker.m.daocloud.io/library/python:3.13-slim"
  }
}

target "app-base" {
  inherits   = ["_platforms"]
  dockerfile = "docker/Dockerfile.base"
  target     = "filex-app-base"
  contexts = {
    "filex-os-base" = "target:os-base"
  }
  args = {
    FILEX_OS_BASE_IMAGE = "filex-os-base"
    PYTHON_IMAGE        = "docker.m.daocloud.io/library/python:3.13-slim"
  }
}

target "extract-base" {
  inherits   = ["_platforms"]
  dockerfile = "docker/Dockerfile.base"
  target     = "filex-extract-base"
  contexts = {
    "filex-os-base" = "target:os-base"
  }
  args = {
    FILEX_OS_BASE_IMAGE = "filex-os-base"
    PYTHON_IMAGE        = "docker.m.daocloud.io/library/python:3.13-slim"
  }
}

target "_app" {
  inherits   = ["_published"]
  dockerfile = "docker/Dockerfile"
  contexts = {
    "filex-app-base" = "target:app-base"
  }
  args = {
    APP_BASE_IMAGE        = "filex-app-base"
    NODE_IMAGE             = "docker.m.daocloud.io/library/node:20-alpine"
    VITE_APP_BUILD_VERSION = SOURCE_TAG
  }
}

target "app-versioned" {
  inherits = ["_app"]
  tags     = ["${REGISTRY}/filex-app:${SOURCE_TAG}"]
}

target "app-stable" {
  inherits = ["_app"]
  tags     = ["${REGISTRY}/filex-app:latest"]
}

target "_kb-extract" {
  inherits   = ["_published"]
  dockerfile = "docker/Dockerfile.extract"
  contexts = {
    "filex-extract-base" = "target:extract-base"
  }
  args = {
    EXTRACT_BASE_IMAGE = "filex-extract-base"
  }
}

target "kb-extract-versioned" {
  inherits = ["_kb-extract"]
  tags     = ["${REGISTRY}/filex-kb-extract:${SOURCE_TAG}"]
}

target "kb-extract-stable" {
  inherits = ["_kb-extract"]
  tags     = ["${REGISTRY}/filex-kb-extract:latest"]
}

target "_postgres" {
  inherits   = ["_published"]
  dockerfile = "docker/Dockerfile.postgres"
  args = {
    BUILD_HTTP_PROXY = ""
  }
}

target "postgres-versioned" {
  inherits = ["_postgres"]
  tags     = ["${REGISTRY}/filex-postgres:pg16-zh-${SOURCE_TAG}"]
}

target "postgres-stable" {
  inherits = ["_postgres"]
  tags     = ["${REGISTRY}/filex-postgres:pg16-zh"]
}
