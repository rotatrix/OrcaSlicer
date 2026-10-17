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


def audit_dependencies(app, executable, binaries):
    """Follow dyld load paths from the app, including inherited LC_RPATH entries."""
    app = app.resolve()
    executable_dir = (app / executable).parent
    visited = set()

    def expand(value, loader):
        for token, directory in (('@loader_path', loader.parent),
                                 ('@executable_path', executable_dir)):
            if value == token or value.startswith(token + '/'):
                return Path(os.path.normpath(str(directory) + value[len(token):]))
        if value.startswith('/'):
            return Path(os.path.normpath(value))
        return None

    def system(path):
        # Runtime system paths also cover SDK framework imports: Mach-O records
        # their system install names, not the developer machine's SDK directory.
        return str(path).startswith(('/usr/lib/', '/System/Library/',
                                     '/Library/Apple/System/Library/'))

    def visit(binary, inherited):
        binary = binary.resolve()
        if binary in visited:
            return
        visited.add(binary)
        loads, rpaths, command = [], [], None
        for line in subprocess.check_output(['otool', '-l', str(binary)], text=True).splitlines():
            line = line.strip()
            if line.startswith('cmd '):
                command = line.split()[1]
            elif command == 'LC_RPATH' and line.startswith('path '):
                value = expand(line[5:].rsplit(' (offset ', 1)[0], binary)
                if value is not None:
                    rpaths.append(value)
            elif command in ('LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB',
                             'LC_LOAD_UPWARD_DYLIB', 'LC_LAZY_LOAD_DYLIB') and line.startswith('name '):
                loads.append(line[5:].rsplit(' (offset ', 1)[0])
        rpaths += inherited
        for dependency in loads:
            if dependency.startswith('/') and system(Path(os.path.normpath(dependency))):
                continue
            if dependency.startswith('@rpath/'):
                candidates = [Path(os.path.normpath(str(base / dependency[7:]))) for base in rpaths]
            elif dependency.startswith(('@loader_path/', '@executable_path/')):
                candidates = [expand(dependency, binary)]
            else:
                candidates = []
            for candidate in candidates:
                if candidate is not None and system(candidate):
                    break
                if candidate is not None and candidate.is_file():
                    if not candidate.resolve().is_relative_to(app):
                        raise ValueError(f'Unbundled non-system dependency: {binary}: {dependency} -> {candidate}')
                    visit(candidate, rpaths)
                    break
            else:
                raise ValueError(f'Unbundled non-system dependency: {binary}: {dependency}')
        return rpaths

    root_rpaths = visit(app / executable, []) or []
    for binary in binaries:
        visit(binary, root_rpaths)


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
        binaries = []
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
                    binaries.append(path)
                    run('lipo', str(path), '-verify_arch', *architectures)
        audit_dependencies(app, executable, binaries)
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
