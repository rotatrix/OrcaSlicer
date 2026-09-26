"""Create a tagged release draft from verified artifacts in this workflow run."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def validate_assets(directory, commit, run_id):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid source commit')
    expected = {
        ('windows-x64', '.zip'), ('windows-x64', '.exe'),
        ('windows-arm64', '.zip'), ('windows-arm64', '.exe'),
        ('macos-universal', '.dmg'),
        ('linux-x64', '.AppImage'), ('linux-aarch64', '.AppImage'),
        ('flatpak-x86_64', '.flatpak'), ('flatpak-aarch64', '.flatpak'),
    }
    assets, found, sdk_commits = [], set(), set()
    for manifest in directory.glob('*.json'):
        data = json.loads(manifest.read_text())
        filename = data['file']
        if Path(filename).name != filename or '/' in filename or '\\' in filename:
            raise ValueError('Invalid package filename')
        package = directory / filename
        kind = (data['platform'], package.suffix)
        if kind not in expected or kind in found:
            raise ValueError(f'Unexpected or duplicate package: {kind}')
        found.add(kind)
        if not package.is_file() or not package.stat().st_size:
            raise ValueError(f'Missing package: {filename}')
        with package.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        checksum = package.with_name(package.name + '.sha256')
        if checksum.read_text().split() != [digest, package.name]:
            raise ValueError(f'Checksum mismatch: {filename}')
        if data.get('commit') != commit or data.get('run_id') != run_id or data.get('sha256') != digest:
            raise ValueError(f'Provenance mismatch: {filename}')
        sdk = data.get('openaxis_commit', '')
        if not re.fullmatch(r'[0-9a-f]{40}', sdk):
            raise ValueError('Invalid SDK revision')
        sdk_commits.add(sdk)
        assets.extend([str(package), str(checksum), str(manifest)])
    if found != expected:
        raise ValueError(f'Missing platform packages: {expected - found}')
    if len(sdk_commits) != 1:
        raise ValueError('Platforms used different SDK revisions')
    return assets


def main():
    commit, run_id, repo = (os.environ[k] for k in ['GITHUB_SHA', 'GITHUB_RUN_ID', 'GH_REPO'])
    assets = validate_assets(Path(sys.argv[1]), commit, run_id)
    if os.environ.get('GITHUB_REF_TYPE') != 'tag':
        raise ValueError('Releases require an explicit release tag')
    tag = os.environ['GITHUB_REF_NAME']
    match = re.fullmatch(r'(v?\d+\.\d+\.\d+)-rotatrix\.([1-9]\d*)(?:-(beta|rc)\.([1-9]\d*))?', tag)
    if not match:
        raise ValueError('Expected <upstream-tag>-rotatrix.N[-beta.N|-rc.N]')
    upstream = match[1]
    version = re.search(r'set\(SoftFever_VERSION "([^"]+)"\)', Path('version.inc').read_text())[1]
    if upstream.removeprefix('v') != version:
        raise ValueError('Release tag does not match the source version')
    tagged_commit = subprocess.check_output(['git', 'rev-parse', f'refs/tags/{tag}^{{commit}}'], text=True).strip()
    if tagged_commit != commit:
        raise ValueError('Release tag does not point to the built commit')
    prerelease = match[3] is not None
    # Include drafts and fail closed on API/auth errors.
    pages = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases'], text=True))
    matches = [release for page in pages for release in page if release['tag_name'] == tag]
    if matches:
        if len(matches) != 1 or not matches[0]['draft'] or matches[0]['prerelease'] != prerelease or matches[0]['target_commitish'] != commit:
            raise ValueError('Existing release is not the matching release draft')
        subprocess.run(['gh', 'release', 'upload', tag, *assets, '--clobber'], check=True)
        return
    notes = f'''OrcaSlicer {tag} - Rotatrix Build (unofficial)

Built from commit {commit}. All three platforms passed compilation, viewport
checks and package smoke checks in the same Actions run:
https://github.com/{repo}/actions/runs/{run_id}

Packages: Windows x64/ARM64 installers and portable ZIPs, macOS universal DMG,
Linux x64/ARM64 AppImages, and x64/ARM64 Flatpaks. Checksums and source manifests
accompany each package.

Windows is unsigned and requires the Microsoft Visual C++ x64 Redistributable.
macOS is ad-hoc signed and not notarized. GUI and Rotatrix hardware testing
remain required before publication. This is not an official OrcaSlicer release.
'''
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'notes.md'
        path.write_text(notes, encoding='utf-8')
        subprocess.run(['gh', 'release', 'create', tag, *assets, '--verify-tag', '--draft',
                        *(['--prerelease'] if prerelease else []),
                        '--target', commit, '--title', f'OrcaSlicer {tag} - Rotatrix Build (unofficial)',
                        '--notes-file', str(path)], check=True)


if __name__ == '__main__':
    main()
