"""Archive upstream app bundles after ad-hoc signing and extraction checks."""
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def package(arch, commit):
    if arch not in ('arm64', 'x86_64', 'universal') or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected architecture and full source SHA')
    architectures = ('arm64', 'x86_64') if arch == 'universal' else (arch,)
    directory = Path('build') / arch / 'OrcaSlicer'
    apps = [('OrcaSlicer.app', arch, 0)]
    if (directory / 'OrcaSlicer_profile_validator.app').exists():
        apps.append(('OrcaSlicer_profile_validator.app', f'profile-validator-{arch}', 1))
    for name, variant, help_status in apps:
        app = directory / name
        with (app / 'Contents/Info.plist').open('rb') as stream:
            info = plistlib.load(stream)
        executable = Path('Contents/MacOS') / info['CFBundleExecutable']
        if name == 'OrcaSlicer.app' and (info['CFBundleIdentifier'] != 'com.orcaslicer.OrcaSlicer'
                                       or info['CFBundleName'] != 'OrcaSlicer'):
            raise ValueError('Main app must retain upstream identity')
        # Reject links to checkout resources and partially merged universal binaries.
        for path in app.rglob('*'):
            if path.is_symlink() and (not path.exists() or not path.resolve().is_relative_to(app.resolve())):
                raise ValueError(f'External or broken bundle symlink: {path}')
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:
                    magic = stream.read(4)
                if magic in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
                             b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                             b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                             b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'):
                    run('lipo', str(path), '-verify_arch', *architectures)
        licenses = app / 'Contents/Resources'
        licenses.mkdir(parents=True, exist_ok=True)
        shutil.copy2('LICENSE.txt', licenses / 'LICENSE.txt')
        run('codesign', '--force', '--deep', '--sign', '-', str(app))
        archive = Path(f'macos-app-{variant}-{commit}.tar.gz').resolve()
        run('tar', '-czf', str(archive), '-C', str(directory), name,
            env={**os.environ, 'COPYFILE_DISABLE': '1'})
        with tempfile.TemporaryDirectory() as temp:
            run('tar', '-xzf', str(archive), '-C', temp)
            if [p.name for p in Path(temp).iterdir()] != [name]:
                raise ValueError('Archive must contain exactly one app')
            extracted = Path(temp) / name
            run('codesign', '--verify', '--deep', '--strict', str(extracted))
            # Universal is smoke-tested on the runner's native architecture;
            # each architecture has its own extracted-package check before merging.
            command = [str(extracted / executable), '--help']
            if arch != 'universal':
                command = ['arch', '-' + arch, *command]
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True, timeout=120)
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            if result.returncode != help_status or (help_status == 1 and 'Orca Profile Validator' not in result.stdout):
                raise RuntimeError(f'{name} help check failed: {result.returncode}')


if __name__ == '__main__':
    package(*sys.argv[1:])
