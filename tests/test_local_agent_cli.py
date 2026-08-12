"""Public CLI help is a portable, complete operator contract."""

import argparse

import pytest

from relay.local_agent_cli import build_parser, main


def test_every_public_long_option_has_ascii_help_and_required_descriptions():
    """Removing a long-option description or adding non-ASCII help breaks the CLI contract."""
    parser = build_parser()
    required = {
        "--max-tokens",
        "--temperature",
        "--seed",
        "--serve-url",
        "--ollama-url",
        "--allow-write",
        "--max-steps",
    }
    long_actions = {
        option: action
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--")
    }

    assert required <= long_actions.keys()
    assert all(action.help and action.help is not argparse.SUPPRESS
               for action in long_actions.values())
    assert parser.format_help().isascii()


def test_help_exits_successfully_with_ascii_output(capsys):
    """The CLI help handler must remain portable and successful."""
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    assert capsys.readouterr().out.isascii()
