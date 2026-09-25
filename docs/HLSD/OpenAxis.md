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

## Preview builds

`.github/workflows/openaxis-build.yml` builds Windows x64, macOS ARM64, and
Linux x64 packages on pushes to `rotatrix/2.4.2`. Manual runs can select a single
platform for debugging. Installed dependencies are cached separately per
platform and dependency-source hash.

After all three builds, overlay checks, and package smoke checks pass, the
workflow creates a draft prerelease. The release gate checks each package's
checksum, full source commit, SDK revision, and workflow run ID; it refuses to
modify a published release. GUI and device testing are still required before
publishing. Windows packages are unsigned; macOS bundles are ad-hoc signed.
