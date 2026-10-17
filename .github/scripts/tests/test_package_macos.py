"""Exercise macOS package dependency validation with real Mach-O libraries."""
import importlib.util
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'package-macos.py'
spec = importlib.util.spec_from_file_location('package_macos', SCRIPT)
package_macos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_macos)


@unittest.skipUnless(platform.system() == 'Darwin', 'Requires macOS compiler and signing tools')
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.arch = platform.machine()
        self.app = Path('build') / self.arch / 'OrcaSlicer/OrcaSlicer.app'
        self.binary = self.app / 'Contents/MacOS/OrcaSlicer'
        self.frameworks = self.app / 'Contents/Frameworks'
        self.binary.parent.mkdir(parents=True)
        (self.frameworks / 'nested').mkdir(parents=True)
        Path('LICENSE.txt').write_text('Fixture license')
        with (self.app / 'Contents/Info.plist').open('wb') as stream:
            plistlib.dump(dict(CFBundleExecutable='OrcaSlicer', CFBundleName='OrcaSlicer',
                              CFBundleIdentifier='com.orcaslicer.OrcaSlicer', CFBundlePackageType='APPL'), stream)
        Path('child.c').write_text('int child(void) { return 0; }')
        Path('parent.c').write_text('int child(void); int parent(void) { return child(); }')
        Path('main.c').write_text('int parent(void); double CFAbsoluteTimeGetCurrent(void); int main(void) { CFAbsoluteTimeGetCurrent(); return parent(); }')
        self.run_cc('-dynamiclib', 'child.c', '-Wl,-install_name,@rpath/libchild.dylib',
                    '-o', str(self.frameworks / 'nested/libchild.dylib'))
        self.run_cc('-dynamiclib', 'parent.c', '-L' + str(self.frameworks / 'nested'), '-lchild',
                    '-Wl,-install_name,@rpath/libparent.dylib', '-Wl,-rpath,@loader_path/nested',
                    '-o', str(self.frameworks / 'libparent.dylib'))
        self.run_cc('main.c', '-framework', 'CoreFoundation', '-Wl,-headerpad_max_install_names', '-L' + str(self.frameworks), '-lparent',
                    '-Wl,-rpath,@executable_path/../Frameworks', '-o', str(self.binary))

    def run_cc(self, *args):
        subprocess.run(['clang', *args], check=True, capture_output=True)

    def test_nested_bundle_rpaths_and_system_libraries(self):
        (self.frameworks / 'alias.dylib').symlink_to('libparent.dylib')
        package_macos.package(self.arch, '0' * 40)
        archive = Path(f'macos-app-{self.arch}-' + '0' * 40 + '.tar.gz')
        with tarfile.open(archive) as stream:
            self.assertEqual({entry.name.split('/')[0] for entry in stream}, {'OrcaSlicer.app'})

    def test_external_library_is_rejected(self):
        external = self.root / 'libexternal.dylib'
        shutil.copy2(self.frameworks / 'libparent.dylib', external)
        subprocess.run(['install_name_tool', '-change', '@rpath/libparent.dylib', str(external),
                        str(self.binary)], check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, 'Unbundled non-system dependency.*libexternal'):
            package_macos.package(self.arch, '0' * 40)

    def test_external_rpath_cannot_shadow_bundled_library(self):
        external = self.root / 'external'
        external.mkdir()
        shutil.copy2(self.frameworks / 'libparent.dylib', external / 'libparent.dylib')
        subprocess.run(['install_name_tool', '-delete_rpath', '@executable_path/../Frameworks',
                        str(self.binary)], check=True, capture_output=True)
        subprocess.run(['install_name_tool', '-add_rpath', str(external),
                        '-add_rpath', '@executable_path/../Frameworks', str(self.binary)],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, 'Unbundled non-system dependency.*external'):
            package_macos.package(self.arch, '0' * 40)

    def test_unresolved_bundle_rpath_is_rejected(self):
        (self.frameworks / 'nested/libchild.dylib').unlink()
        with self.assertRaisesRegex(ValueError, 'Unbundled non-system dependency.*libchild'):
            package_macos.package(self.arch, '0' * 40)


if __name__ == '__main__':
    unittest.main()
