"""Regression checks for the GRUB -> embedded NoCloud seed handoff."""
import importlib.util
from pathlib import Path
import shlex
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('patch_grub', ROOT / 'iso/patch-grub.py')
assert SPEC is not None and SPEC.loader is not None
patch_grub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch_grub)


def kernel_tokens(text):
    line = next(line for line in text.splitlines() if line.lstrip().startswith('linux '))
    lexer = shlex.shlex(line, posix=True, punctuation_chars=';')
    lexer.whitespace_split = True
    return list(lexer)


class InstallerSeedTests(unittest.TestCase):
    def test_embedded_seed_is_selected_and_semicolon_is_quoted(self):
        result, _ = patch_grub.patch_text('linux /casper/vmlinuz quiet ---\n', True, None)
        tokens = kernel_tokens(result)
        self.assertIn('ds=nocloud;s=/cdrom/autoinstall/', tokens)
        self.assertNotIn(';', tokens)

    def test_installer_only_arguments_precede_separator(self):
        result, _ = patch_grub.patch_text('linux /casper/vmlinuz quiet ---\n', True, None)
        tokens = kernel_tokens(result)
        self.assertLess(tokens.index('autoinstall'), tokens.index('---'))

    def test_stale_bare_nocloud_argument_is_repaired(self):
        result, _ = patch_grub.patch_text('linux /casper/vmlinuz --- autoinstall ds=nocloud;\n', True, None)
        tokens = kernel_tokens(result)
        self.assertIn('ds=nocloud;s=/cdrom/autoinstall/', tokens)
        self.assertEqual(tokens.count('autoinstall'), 1)
        self.assertNotIn(';', tokens)

    def test_lan_seed_survives_shell_tokenization(self):
        result, _ = patch_grub.patch_text('linux /casper/vmlinuz ---\n', False, 'http://192.0.2.1:8000/')
        self.assertIn('ds=nocloud-net;s=http://192.0.2.1:8000/', kernel_tokens(result))
        self.assertNotIn(';', kernel_tokens(result))

    def test_second_pass_is_idempotent(self):
        first, _ = patch_grub.patch_text('linux /casper/vmlinuz quiet ---\n', True, None)
        second, count = patch_grub.patch_text(first, True, None)
        self.assertEqual(first, second)
        self.assertEqual(count, 0)

    def test_mode_change_replaces_old_seed(self):
        first, _ = patch_grub.patch_text('linux /casper/vmlinuz ---\n', True, None)
        result, _ = patch_grub.patch_text(first, False, 'http://192.0.2.2:8000/')
        seeds = [item for item in kernel_tokens(result) if item.startswith('ds=')]
        self.assertEqual(seeds, ['ds=nocloud-net;s=http://192.0.2.2:8000/'])

    def test_noninstaller_kernel_is_untouched(self):
        line = 'linux /vmlinuz root=UUID=example quiet'
        result, count = patch_grub.patch_text(line, True, None)
        self.assertIn(line, result.splitlines())
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
