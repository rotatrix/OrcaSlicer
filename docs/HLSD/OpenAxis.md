# OpenAxis navigation

Enable the optional native GUI integration with `-DSLIC3R_OPENAXIS=ON` when
configuring OrcaSlicer. CMake 3.24 or newer fetches the OpenAxis C++ SDK at
`cpp/v1.0.0-rc.1`; `-DOPENAXIS_SOURCE_DIR=/path/to/openaxis` uses a local checkout.
The normal OrcaSlicer dependencies are still required. With the option off,
the application does not fetch or link the SDK. The integration supplies the SDK
with OrcaSlicer's bundled JSON target so both use the same JSON types and ABI.

The SDK connects to Rotatrix on localhost and schedules navigation on the wx UI
thread. Each viewport owns its connection and cancels gestures when focus,
model, plate, dimensions, or scene revision change. Pose writes use the native
camera and projection calculation, returning the realized pose after clamping;
native camera changes are reconciled with the session.

Picks use the existing mesh raycasters without changing native hover state.
Plate body meshes participate in ordinary picks; plate toolbar icons and gizmos
do not. Selection picks use selected model volumes. Plate placement is already
baked into its picking mesh and must not be translated again.

Help > OpenAxis Diagnostics opens a compact connection, focus, and gesture panel.
Viewport evidence is enabled while the panel is open; the pivot remains visible
independently. Logs are available in the external Rotatrix log viewer.

## Verification

The dependency-free overlay checks cover clipping, perspective division, DPI,
and viewport offsets:

```
cmake -S tests/openaxis -B build_openaxis_checks
cmake --build build_openaxis_checks --config Release
ctest --test-dir build_openaxis_checks -C Release --output-on-failure
```

In a GUI build, verify rotation, pan, zoom, native mouse input after navigation,
plate switching, selection-only picking, and focus loss in Prepare and Preview.
Open and close the diagnostics panel and confirm viewport evidence follows it.

## Fork branches and builds

The current port is development work on `rotatrix/work/v2.4.2`, based on the
exact upstream `v2.4.2` tag. Work branches are disposable and may be rebased or
squashed. When ready, organize the downstream changes into a clean patch stack
and create `rotatrix/v2.4.2`. Published maintained branches are append-only;
contributors open PRs against the relevant maintained branch. A new upstream
version starts a new work branch from its own official tag.

The default branch is temporarily the work branch while no maintained Rotatrix
branch exists. Set it to `rotatrix/v2.4.2` on promotion. There is no rolling
`rotatrix/stable` branch. Mirror upstream tag spelling, including the `v`.

## Upstream CI migration

The source and workflow baseline is official OrcaSlicer `v2.4.2`, commit
`8500fcdccaa10b5099ac20d252af3a7c560046f1`; the workflows are adapted from that
release, not copied from upstream main. Its dependency definitions, build
options and architecture coverage are retained. Windows Store packaging remains
upstream-only because its publisher identity is not Rotatrix's.

Compatibility adjustments are separate from the OpenAxis and branding commits:
Windows x64 uses `windows-2022` and an explicit MSVC environment; Perl is selected
explicitly for dependency builds. Windows ARM64 predeclares the unavailable
Fortran compiler for Eigen, avoiding a hung Visual Studio probe while retaining
Eigen's normal no-Fortran path. macOS retains `macos-14`, exports the selected
SDK and Homebrew tools, and keeps the active Xcode installation. Linux dependency
archives use the build script's `OrcaSlicer_dep` directory. Flatpak uses the
container's Python and a scoped Git ownership exception for provenance. Build
parallelism is bounded on hosted runners. No additional upstream compatibility
commits were cherry-picked. The release's placeholder-parser vector test needs
explicit vector fixtures because its production settings are scalar; assertions
and production behavior are unchanged. Reassess these adjustments and the
external regression-suite pin when porting to a newer release.

`build_all.yml` is the active pipeline, reusing upstream's `build_check_cache.yml`
-> `build_deps.yml` -> `build_orca.yml` chain. It runs on Rotatrix branch pushes,
PRs against maintained branches, and manual dispatch. Manual runs can select a
platform family for isolated retries. The upstream matrix builds
Windows x64/ARM64, Linux x64/ARM64, macOS arm64/x86_64 plus a universal DMG, and
Flatpak x64/ARM64. Upstream Linux unit/regression tests are retained. The external
regression suite is pinned to its last revision before the upstream release;
update that pin when porting to another upstream version. OpenAxis
checks and native startup checks run before distribution artifacts are uploaded.

OpenAxis is opt-in for local builds. CI uses the SDK release specified in
`cmake/OpenAxis.cmake`, includes its licenses, and enables it through upstream
build scripts. Flatpak uses the same pinned SDK as an offline manifest source;
update its commit when updating the SDK tag. Windows Store identity and upstream
nightly publication remain restricted to the upstream repository. Test macOS
bundles are ad-hoc signed; production signing needs Rotatrix credentials.

Artifacts include the source SHA, checksums and source/SDK/run manifests, and
expire after 14 days. Routine branch/PR builds do not create releases or tags.
An explicit immutable `<upstream-tag>-rotatrix.N` tag triggers a full build and
calls the adapted upstream `publish_release.yml`. Every distribution and test
job must pass; the release script verifies all nine distributions are from the
same source, SDK and run before creating a draft. Final tags create regular
drafts; `-beta.N`/`-rc.N` tags create prerelease drafts. Published releases are
never overwritten. No release tags are created automatically. Reset N when the
upstream version changes. GUI and hardware testing remain required.

During migration, `openaxis-build.yml` remains a manual-only fallback. Retire
that workflow and its standalone packaging scripts only after the upstream
pipeline passes with downloadable packages. No maintained branch or release
is created as part of this migration.
