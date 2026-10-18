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
camera while preserving the user's projection preference. The native orbit target
stays on the viewing axis at the pivot's depth, including off-center pivots.
Close-range navigation clips near-eye geometry instead of moving the camera away;
native fit-to-bed/object restores normal scene fitting. Writes return the realized
pose, and native camera changes are reconciled with the session.

Picks use the existing mesh raycasters without changing native hover state.
Plate body meshes participate in ordinary picks; plate toolbar icons and gizmos
do not. Selection picks use selected model volumes. Plate placement is already
baked into its picking mesh and must not be translated again.
G-code Preview registers the current plate body without its toolbar icons.

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

## Download and build identity

Rotatrix distributions use the upstream application identity and share its settings.
Windows downloads are unsigned. macOS preview build artifacts are ad-hoc signed;
release downloads use Developer ID signing and notarization.

The SDK source is https://github.com/rotatrix/openaxis at `cpp/v1.0.0-rc.1`
(`acc4da095cde6747556245b4b6c110c16b968b6b`). Its bundled IXWebSocket license
and the OpenAxis license are included in packaged resources. OrcaSlicer's
dependency versions, source URLs and patches remain in `deps/` and `deps_src/`.

The macOS build excludes third-party prefixes with a semicolon-separated CMake
ignore list. If an existing build retained XQuartz OpenGL paths, reconfigure
affected dependency and app caches with `-U'OPENGL_*'` and the corrected
`CMAKE_IGNORE_PREFIX_PATH`, then rebuild the affected targets.
