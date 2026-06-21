"""Tests for shell input parsing and command translation."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from icepi_helper import split_shell_words, translate_shell_words, ShellInputError


def test_split_simple():
    assert split_shell_words("flash jedec") == ["flash", "jedec"]


def test_split_quoted():
    assert split_shell_words('install "my project"') == ["install", "my project"]


def test_split_unterminated_quote():
    try:
        split_shell_words('install "unclosed')
        assert False, "should have raised"
    except ShellInputError:
        pass


def test_translate_help():
    # The live session loop intercepts help/? before translation;
    # translate passes them through unchanged.
    assert translate_shell_words(["help"]) == ["help"]
    assert translate_shell_words(["help", "flash"]) == ["help", "flash"]
    assert translate_shell_words(["?"]) == ["?"]


def test_translate_quit():
    # quit/exit are intercepted by the live session loop, not translated.
    assert translate_shell_words(["exit"]) == ["exit"]
    assert translate_shell_words(["quit"]) == ["quit"]


def test_translate_flash():
    assert translate_shell_words(["flash", "jedec"]) == ["flash-jedec"]
    assert translate_shell_words(["flash", "status"]) == ["flash-status"]
    assert translate_shell_words(["flash", "read", "0", "64"]) == ["flash-read", "0", "64"]
    assert translate_shell_words(["flash", "clear-error"]) == ["flash-clear-error"]


def test_translate_sd():
    assert translate_shell_words(["sd", "info"]) == ["sd-info"]
    assert translate_shell_words(["sd", "init"]) == ["sd-init"]
    assert translate_shell_words(["sd", "layout"]) == ["sd-layout"]
    assert translate_shell_words(["sd", "read", "0"]) == ["sd-read", "0"]


def test_translate_sd_fs():
    assert translate_shell_words(["sd", "fs", "info"]) == ["sd-fs-info"]
    assert translate_shell_words(["sd", "fs", "ls", "/"]) == ["sd-fs-ls", "/"]
    assert translate_shell_words(["sd", "fs", "cat", "/test.bin"]) == ["sd-fs-cat", "/test.bin"]


def test_translate_sd_auto():
    assert translate_shell_words(["sd", "auto", "info"]) == ["sd-auto-info"]
    assert translate_shell_words(["sd", "auto", "arm", "foo"]) == ["sd-auto-arm", "foo"]
    assert translate_shell_words(["sd", "auto", "clear"]) == ["sd-auto-clear"]


def test_translate_sd_boot():
    assert translate_shell_words(["sd", "boot", "info"]) == ["sd-auto-info"]
    assert translate_shell_words(["sd", "boot", "arm", "foo"]) == ["sd-auto-arm", "foo"]


def test_translate_slot():
    assert translate_shell_words(["slot", "show", "boot"]) == ["slot-show", "boot"]
    assert translate_shell_words(["slot", "list"]) == ["slots"]


def test_translate_project():
    assert translate_shell_words(["project", "list"]) == ["build", "--list"]


def test_translate_board():
    assert translate_shell_words(["board", "test"]) == ["board-test"]


def test_translate_service():
    assert translate_shell_words(["service", "probe"]) == ["probe"]
    assert translate_shell_words(["service", "debug"]) == ["debug"]
    assert translate_shell_words(["service", "clear-error"]) == ["clear-error"]
    assert translate_shell_words(["service", "enter"]) == ["info", "--enter-service"]
    assert translate_shell_words(["service", "exit"]) == ["probe"]
    assert translate_shell_words(["service"]) == ["info", "--enter-service"]


def test_translate_passthrough():
    assert translate_shell_words(["status"]) == ["status"]
    assert translate_shell_words(["info", "--enter-service"]) == ["info", "--enter-service"]
    assert translate_shell_words(["reload"]) == ["reload"]


def test_translate_empty():
    assert translate_shell_words([]) == []
