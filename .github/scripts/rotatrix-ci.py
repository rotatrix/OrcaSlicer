"""Small OpenAxis additions around upstream build and packaging commands."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def run(*args):
    subprocess.run(args, check=True)


def prepare():
    tag = re.search(r'GIT_TAG\s+(\S+)', Path('cmake/OpenAxis.cmake').read_text())[1]
    sdk = Path(os.environ['RUNNER_TEMP']) / 'openaxis-sdk'
    run('git', 'clone', '--depth', '1', '--branch', tag, 'https://github.com/rotatrix/openaxis.git', str(sdk))
    revision = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'], text=True).strip()
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as env:
        env.write(f'SLIC3R_OPENAXIS=ON\nOPENAXIS_SOURCE_DIR={sdk.as_posix()}\nOPENAXIS_COMMIT={revision}\n')
        env.write(f'ORCA_EXTRA_BUILD_ARGS=-DSLIC3R_OPENAXIS=ON -DOPENAXIS_SOURCE_DIR={sdk.as_posix()}\n')
    shutil.copy2(sdk / 'LICENSE', 'resources/OpenAxis-LICENSE.txt')
    shutil.copy2(sdk / 'cpp/third_party/ixwebsocket/LICENSE.txt', 'resources/OpenAxis-IXWebSocket-LICENSE.txt')


def verify(platform, arch):
    build = Path('build')
    if platform == 'macos':
        build /= arch
    elif platform == 'windows' and arch == 'arm64':
        build = Path('build-arm64')
    if 'SLIC3R_OPENAXIS:BOOL=ON' not in (build / 'CMakeCache.txt').read_text():
        raise ValueError('OpenAxis was not enabled')
    checks = build / 'openaxis-checks'
    run('cmake', '-S', 'tests/openaxis', '-B', str(checks), '-DCMAKE_BUILD_TYPE=Release')
    run('cmake', '--build', str(checks), '--config', 'Release', '--parallel', '2')
    run('ctest', '--test-dir', str(checks), '-C', 'Release', '--output-on-failure')
    if platform == 'windows':
        command = [str((build / 'OrcaSlicer/orca-slicer.exe').resolve()), '--help']
    elif platform == 'macos':
        app = build / 'OrcaSlicer/OrcaSlicer.app'
        run('codesign', '--force', '--deep', '--sign', '-', str(app))
        run('codesign', '--verify', '--deep', '--strict', str(app))
        command = ['arch', '-'+arch, str(app / 'Contents/MacOS/OrcaSlicer'), '--help']
    else:
        images = list(build.glob('OrcaSlicer_Linux_AppImage*.AppImage'))
        if len(images) != 1:
            raise ValueError(f'Expected one AppImage: {images}')
        command = ['xvfb-run', '-a', str(images[0]), '--appimage-extract-and-run', '--help']
    subprocess.run(command, check=True, timeout=120)


def record(platform, arch):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if commit != os.environ['GITHUB_SHA']:
        raise ValueError('Checkout differs from workflow source SHA')
    sdk = os.environ['OPENAXIS_COMMIT']
    if platform == 'windows':
        build = Path('build-arm64' if arch == 'arm64' else 'build')
        patterns = [f'{build}/OrcaSlicer_Windows_*_portable.zip', f'{build}/OrcaSlicer_Windows_Installer_*.exe']
    elif platform == 'macos':
        patterns = ['OrcaSlicer_Mac_universal_*.dmg']
        app = 'build/universal/OrcaSlicer/OrcaSlicer.app'
        run('lipo', '-verify_arch', 'arm64', 'x86_64', f'{app}/Contents/MacOS/OrcaSlicer')
        run('codesign', '--verify', '--deep', '--strict', app)
    elif platform == 'linux':
        patterns = ['build/OrcaSlicer_Linux_AppImage*.AppImage']
    elif platform == 'flatpak':
        manifest = Path('scripts/flatpak/com.orcaslicer.OrcaSlicer.yml').read_text()
        if f'commit: {sdk}' not in manifest:
            raise ValueError('Flatpak SDK pin differs from native builds')
        patterns = [f'OrcaSlicer-Linux-flatpak_*_{arch}.flatpak']
    else:
        raise ValueError(platform)
    for pattern in patterns:
        packages = list(Path('.').glob(pattern))
        if len(packages) != 1:
            raise ValueError(f'Expected exactly one package for {pattern}: {packages}')
        package = packages[0]
        if not package.stat().st_size:
            raise ValueError('Empty package')
        with package.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        package.with_name(package.name + '.sha256').write_text(f'{digest}  {package.name}\n')
        package.with_name(package.name + '.json').write_text(json.dumps(dict(
            commit=commit, openaxis_commit=sdk, run_id=os.environ['GITHUB_RUN_ID'],
            platform=f'{platform}-{arch}', file=package.name, sha256=digest), indent=2)+'\n')


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'verify':
        verify(*sys.argv[2:])
    elif sys.argv[1] == 'record':
        record(*sys.argv[2:])
    else:
        raise SystemExit('Unknown command')
