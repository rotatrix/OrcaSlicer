"""Small OpenAxis additions around upstream build and packaging commands."""
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
    generator = ['-G', 'Ninja Multi-Config'] if platform == 'windows' and arch == 'arm64' else []
    run('cmake', '-S', 'tests/openaxis', '-B', str(checks), '-DCMAKE_BUILD_TYPE=Release', *generator)
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


def stage(platform, arch):
    """Give native packages stable, exact-SHA download names without repacking."""
    commit = os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected full source SHA')
    actual = subprocess.check_output(['git', '-c', f'safe.directory={Path.cwd().as_posix()}', 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise ValueError('Checkout differs from workflow commit')
    if platform == 'windows' and arch == 'x64':
        patterns = ['build/OrcaSlicer_Windows_*_portable.zip', 'build/OrcaSlicer_Windows_Installer_*.exe']
    elif platform == 'linux' and arch == 'x64':
        patterns = ['build/OrcaSlicer_Linux_AppImage*.AppImage']
    elif platform == 'flatpak' and arch == 'x86_64':
        manifest = Path('scripts/flatpak/com.orcaslicer.OrcaSlicer.yml').read_text()
        if f"commit: {os.environ['OPENAXIS_COMMIT']}" not in manifest:
            raise ValueError('Flatpak SDK differs from native builds')
        patterns = ['OrcaSlicer-Linux-flatpak_*_x86_64.flatpak']
        platform = 'linux'
    else:
        raise ValueError('Unsupported distribution platform')
    output = Path('artifacts')
    output.mkdir(exist_ok=True)
    for pattern in patterns:
        packages = list(Path('.').glob(pattern))
        if len(packages) != 1 or not packages[0].stat().st_size:
            raise ValueError(f'Expected one nonempty package: {pattern}')
        package = packages[0]
        shutil.copy2(package, output / f'OrcaSlicer-{platform}-x64-{commit}{package.suffix}')


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'verify':
        verify(*sys.argv[2:])
    elif sys.argv[1] == 'stage':
        stage(*sys.argv[2:])
    else:
        raise SystemExit('Unknown command')
