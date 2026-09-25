"""Create a draft only from verified artifacts produced by this workflow run."""
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
    assets = []
    sdk_commits = set()
    for platform, extension in [('windows-x64', 'zip'), ('macos-arm64', 'zip'), ('linux-x64', 'AppImage')]:
        package = directory / f'OrcaSlicer-Rotatrix-{platform}-{commit[:12]}.{extension}'
        checksum = package.with_name(package.name + '.sha256')
        manifest = package.with_name(package.name + '.json')
        if not package.is_file() or package.stat().st_size == 0:
            raise ValueError(f'Missing package: {package}')
        with package.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if checksum.read_text().split() != [digest, package.name]:
            raise ValueError(f'Checksum mismatch: {package}')
        data = json.loads(manifest.read_text())
        expected = dict(commit=commit, run_id=run_id, platform=platform, file=package.name, sha256=digest)
        if any(data.get(k) != v for k, v in expected.items()):
            raise ValueError(f'Provenance mismatch: {package}')
        sdk = data.get('openaxis_commit', '')
        if not re.fullmatch(r'[0-9a-f]{40}', sdk):
            raise ValueError('Invalid SDK revision')
        sdk_commits.add(sdk)
        assets.extend([str(package), str(checksum), str(manifest)])
    if len(sdk_commits) != 1:
        raise ValueError('Platforms used different SDK revisions')
    return assets


def main():
    commit, run_id, repo = (os.environ[k] for k in ['GITHUB_SHA', 'GITHUB_RUN_ID', 'GH_REPO'])
    assets = validate_assets(Path(sys.argv[1]), commit, run_id)
    tag = f'openaxis-preview-{commit}'
    # Include drafts and fail closed on API/auth errors.
    pages = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases'], text=True))
    matches = [release for page in pages for release in page if release['tag_name'] == tag]
    if matches:
        if len(matches) != 1 or not matches[0]['draft'] or not matches[0]['prerelease'] or matches[0]['target_commitish'] != commit:
            raise ValueError('Existing release is not the matching draft prerelease')
        subprocess.run(['gh', 'release', 'upload', tag, *assets, '--clobber'], check=True)
        return
    notes = f'''OrcaSlicer 2.4.2 — Rotatrix Build (unofficial)

Built from commit {commit}. All three platforms passed compilation, viewport
checks and package smoke checks in the same Actions run:
https://github.com/{repo}/actions/runs/{run_id}

Packages: Windows x64 portable ZIP, macOS ARM64 app ZIP, and Linux x64 AppImage
for Ubuntu 24.04 and compatible distributions. Checksums and source manifests
accompany each package.

Windows is unsigned and requires the Microsoft Visual C++ x64 Redistributable.
macOS is ad-hoc signed and not notarized. GUI and Rotatrix hardware testing
remain required before publication. This is not an official OrcaSlicer release.
'''
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'notes.md'
        path.write_text(notes, encoding='utf-8')
        subprocess.run(['gh', 'release', 'create', tag, *assets, '--draft', '--prerelease',
                        '--target', commit, '--title', f'OrcaSlicer 2.4.2 OpenAxis preview {commit[:12]}',
                        '--notes-file', str(path)], check=True)


if __name__ == '__main__':
    main()
