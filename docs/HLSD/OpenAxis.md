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

`.github/workflows/openaxis-build.yml` runs on pushes to `rotatrix/**`, PRs
against `rotatrix/*`, and manual dispatch (including a single-platform option).
It builds Windows x64, macOS ARM64, and Linux x64, using upstream dependency,
build and AppImage scripts. Existing upstream workflows are retained, including
the broader architecture matrix and installer/signing/notarization machinery;
the current OpenAxis test pipeline uses the three validated native targets.
Installed dependencies are cached per platform and dependency-source hash.
Artifacts include the full source SHA and expire after 14 days. Ordinary work,
maintained-branch and PR builds never create a release or tag.

Release builds run only when an explicit `<upstream-tag>-rotatrix.N` tag is
pushed, for example `v2.4.2-rotatrix.1`. Reset N for each upstream version.
Tags are immutable: never move or delete a shipped release tag. Permanent test
releases use `v2.4.2-rotatrix.1-beta.1` (or `-rc.1`) and are prereleases.
All three platform jobs must succeed in the same run. The release gate checks
checksums, source SHA, SDK revision, run ID and tag target before creating a
draft; it refuses to overwrite a published release. Final tags create regular
drafts, beta/rc tags create prerelease drafts. No release tag is created by CI.

The current work-stage packages are a Windows portable ZIP, a macOS app ZIP and
a Linux AppImage. Windows is unsigned and macOS is ad-hoc signed, not notarized.
Before shipping a maintained release, adapt the retained upstream installer and
signing/notarization workflow with Rotatrix credentials; upstream signing secrets
are not available to this fork. GUI and device testing remain required. Drafts
must not be treated as production-ready signed distributions.
