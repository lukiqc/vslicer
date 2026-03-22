"""Keyboard controls for VSlicer.

Simple command-based control system for interacting with video playback.
"""

from typing import Literal

ControlAction = Literal[
    "play_pause",
    "frame_forward",
    "frame_backward",
    "mark_in",
    "mark_out",
    "export",
    "help",
    "quit",
    "unknown",
]


def parse_input(user_input: str) -> ControlAction:
    """Parse user input into control action.

    Args:
        user_input: User input string

    Returns:
        Control action
    """
    user_input = user_input.strip().lower()

    # Map inputs to actions
    action_map = {
        " ": "play_pause",
        "space": "play_pause",
        ".": "frame_forward",
        ">": "frame_forward",
        ",": "frame_backward",
        "<": "frame_backward",
        "i": "mark_in",
        "o": "mark_out",
        "e": "export",
        "h": "help",
        "?": "help",
        "q": "quit",
        "quit": "quit",
        "exit": "quit",
    }

    return action_map.get(user_input, "unknown")


def display_prompt() -> str:
    """Display control prompt and get user input.

    Returns:
        User input string
    """
    return input("\n>>> Type command here (h=help, q=quit): ").strip()
