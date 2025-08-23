"""
This module contains miscellaneous utility functions for the GUI,
such as functions that interact with the user's desktop environment.
"""
import easygui

def open_file_dialog():
    """
    Opens a native file dialog to select a file.
    """
    try:
        file_path = easygui.fileopenbox()
        return file_path
    except Exception as e:
        # This can happen in environments without a display server
        print(f"Could not open file dialog: {e}")
        # In a real app, you might return a specific error message
        # or handle it more gracefully. For now, we return None.
        return None
