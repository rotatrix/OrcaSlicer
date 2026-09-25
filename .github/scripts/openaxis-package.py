"""Archive the tested platform package and record its exact source revision."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

platform = sys.argv[1]
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
if os.environ.get('GITHUB_SHA', commit) != commit:
    raise SystemExit('Checkout differs from the Actions source commit')
build = Path('build/arm64' if platform == 'macos-arm64' else 'build')
sdk_source = build / '_deps/openaxis-src'
# Include the licenses for the SDK and its bundled websocket implementation.
resources = Path('resources')
for filename, source in [('OpenAxis-LICENSE.txt', sdk_source / 'LICENSE'),
                         ('OpenAxis-IXWebSocket-LICENSE.txt', sdk_source / 'cpp/third_party/ixwebsocket/LICENSE.txt')]:
    destination = (Path('build/OrcaSlicer/resources') if platform == 'windows-x64' else
                   Path('build/arm64/OrcaSlicer/OrcaSlicer.app/Contents/Resources') if platform == 'macos-arm64' else resources)
    shutil.copy2(source, destination / filename)
if platform == 'linux-x64':
    subprocess.run(['bash', './src/build_linux_image.sh', '-i', '-R', 'Release'], cwd='build', check=True)
elif platform == 'macos-arm64':
    app = 'build/arm64/OrcaSlicer/OrcaSlicer.app'
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', app], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', app], check=True)
name = f'OrcaSlicer-Rotatrix-{platform}-{commit[:12]}'
dist = Path('dist')
dist.mkdir(exist_ok=True)
if platform == 'windows-x64':
    source = Path('build/OrcaSlicer')
    if not (source / 'orca-slicer.exe').is_file():
        raise SystemExit('Missing installed Windows executable')
    shutil.make_archive(str(dist / name), 'zip', source.parent, source.name)
    package = dist / (name + '.zip')
    build = Path('build')
elif platform == 'macos-arm64':
    source = Path('build/arm64/OrcaSlicer/OrcaSlicer.app')
    package = dist / (name + '.zip')
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(source), str(package)], check=True)
    build = Path('build/arm64')
elif platform == 'linux-x64':
    images = list(Path('build').glob('OrcaSlicer_Linux_*.AppImage'))
    if len(images) != 1:
        raise SystemExit(f'Expected exactly one AppImage, found {images}')
    package = dist / (name + '.AppImage')
    shutil.copy2(images[0], package)
    subprocess.run(['xvfb-run', '-a', str(package), '--appimage-extract-and-run', '--help'], check=True, timeout=120)
    build = Path('build')
else:
    raise SystemExit('Unknown platform')
cache = (build / 'CMakeCache.txt').read_text()
if 'SLIC3R_OPENAXIS:BOOL=ON' not in cache:
    raise SystemExit('OpenAxis is not enabled in this build')
sdk = subprocess.check_output(['git', '-C', str(build / '_deps/openaxis-src'), 'rev-parse', 'HEAD'], text=True).strip()
with package.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
package.with_name(package.name + '.sha256').write_text(f'{digest}  {package.name}\n')
package.with_name(package.name + '.json').write_text(json.dumps({
    'commit': commit, 'openaxis_commit': sdk, 'platform': platform,
    'file': package.name, 'sha256': digest,
    'run_id': os.environ.get('GITHUB_RUN_ID'),
}, indent=2) + '\n')
print(f'{package}: {digest}')
