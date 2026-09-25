#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
platform=${1:?Platform required}
stage=${2:?Stage required}
export CMAKE_BUILD_PARALLEL_LEVEL=${CMAKE_BUILD_PARALLEL_LEVEL:-2}
export git_commit_hash=${GITHUB_SHA:-$(git rev-parse HEAD)}
if [[ "$platform" == macos ]]; then
  export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
  export PATH="$(brew --prefix)/opt/gettext/bin:$(brew --prefix)/opt/texinfo/bin:$PATH"
fi
if [[ "$stage" == deps ]]; then
  case "$platform" in
    linux) ./build_linux.sh -drlL ;;
    macos) ./build_release_macos.sh -dx -a arm64 -t 11.3 ;;
    *) exit 2 ;;
  esac
elif [[ "$stage" == build ]]; then
  case "$platform" in
    linux)
      export ORCA_EXTRA_BUILD_ARGS='-DSLIC3R_OPENAXIS=ON -DOPENAXIS_SOURCE_DIR='
      ./build_linux.sh -srlL
      ./scripts/check_appimage_libs.sh ./build/package ./build/package/bin/orca-slicer
      xvfb-run -a ./build/package/orca-slicer --help
      ;;
    macos)
      export SLIC3R_OPENAXIS=ON
      ./build_release_macos.sh -sx -a arm64 -t 11.3
      app=build/arm64/OrcaSlicer/OrcaSlicer.app
      codesign --force --deep --sign - "$app"
      codesign --verify --deep --strict "$app"
      "$app/Contents/MacOS/OrcaSlicer" --help
      ;;
    *) exit 2 ;;
  esac
  cmake -S tests/openaxis -B build/openaxis-checks -G Ninja -DCMAKE_BUILD_TYPE=Release
  cmake --build build/openaxis-checks
  ctest --test-dir build/openaxis-checks --output-on-failure
else
  exit 2
fi
