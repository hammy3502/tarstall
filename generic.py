"""tarstall: A package manager for managing archives
    Copyright (C) 2019  hammy3502

    tarstall is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    tarstall is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with tarstall.  If not, see <https://www.gnu.org/licenses/>."""

import sys
import config
import os

if config.mode == "gui":
    try:
        import PySimpleGUI as sg
    except ImportError:
        pass  # This will be caught by tarstall.py, let's not worry about it here.

def ask(question):
    """Get Any User Input.

    Get user input, with no expected response like with get_input

    Args:
        question (str): Question to ask user

    Returns:
        str: User-supplied answer to question
    
    """
    if config.mode == "cli":
        return input(question)
    elif config.mode == "gui":
        layout = [
            [sg.Text(question)],
            [sg.InputText(key="answer"), sg.Button("Submit")]
        ]
        window = sg.Window("tarstall-gui", layout, disable_close=True)
        while True:
            event, values = window.read()
            if event == "Submit":
                window.Close()
                return values["answer"]


def ask_file(question):
    """Get User Input for File.

    Get user input for a file

    Args:
        question (str): Question to ask user

    Returns:
        str: Path to file
    
    """
    if config.mode == "cli":
        f = "asdf"
        while not config.exists(config.full(f)):
            f = input(question)
        return config.full(f)
    elif config.mode == "gui":
        layout = [
            [sg.Text(question)],
            [sg.InputText(key="answer"), sg.FileBrowse()],
            [sg.Button("Submit")]
        ]
        window = sg.Window("tarstall-gui", layout, disable_close=True)
        while True:
            event, values = window.read()
            if event == "Submit":
                window.Close()
                return values["answer"]


def get_input(question, options, default, gui_labels=[]):
    """Get User Input.

    Get user input, except make sure the input provided matches one of the options we're looking for

    Args:
        question (str): Question to ask the user
        options (str[]): List of options the user can choose from
        default (str): Default option (used when user enters nothing)
        gui_labels (str[]): Labels to use for GUI buttons/dropdown menus (optional)

    Returns:
        str: Option the user chose

    """
    if config.mode == "cli":
        options_form = list(options)  # Otherwise, Python would "link" options_form with options
        options_form[options_form.index(default)] = options_form[options_form.index(default)].upper()
        if len(options) > 3:
            question += "\n[" + "/".join(options_form) + "]"
        else:
            question += " [" + "/".join(options_form) + "]"
        answer = "This is a string. There are many others like it, but this one is mine."  # Set answer to something
        while answer not in options and answer != "":
            answer = input(question)
            answer = answer.lower()  # Loop ask question while the answer is invalid or not blank
        if answer == "":
            return default  # If answer is blank return default answer
        else:
            return answer  # Return answer if it isn't the default answer
    elif config.mode == "gui":
        if gui_labels == []:
            gui_labels = options
        if len(options) <= 5:
            button_list = []
            for o in gui_labels:
                button_list.append(sg.Button(o))
            layout = [
                [sg.Text(question)],
                button_list
            ]
            window = sg.Window("tarstall-gui", layout, disable_close=True)
            while True:
                event, values = window.read()
                if event in gui_labels:
                    window.Close()
                    return options[gui_labels.index(event)]
        else:
            layout = [
                [sg.Text(question)],
                [sg.Combo(gui_labels, key="option"), sg.Button("Submit")]
            ]
            window = sg.Window("tarstall-gui", layout, disable_close=True)
            while True:
                event, values = window.read()
                if event == "Submit":
                    window.Close()
                    return options[gui_labels.index(values["option"])]



def endi(state):
    """Bool to String.

    Args:
        state (bool): Bool to convert

    Returns:
        str: "enabled" if True, "disabled" if False

    """
    if state:
        return "enabled"
    else:
        return "disabled"


def pprint(st, title="tarstall-gui"):
    """Print Depending on Mode.

    Args:
        st (str): String to print or display in GUI popup.
        title (str, optional): Title for window if in GUI mode. Defaults to "tarstall-gui".

    """
    if config.mode == "gui":
        sg.Popup(st, title=title)
    elif config.mode == "cli":
        print(st)


def progress(val, should_show=True):
    """Update Progress of Operation.

    Updates a progress bar (if we have a GUI) as tarstall processes run

    Args:
        val (int): Value to update the progress bar to.
        should_show (bool): If set to False, don't show the bar in CLI. Defaults to True.

    """
    if config.mode == "gui":
        if config.install_bar is not None:
            config.install_bar.UpdateBar(val)
    elif config.mode == "cli" and not config.verbose and should_show:
        try:
            columns = int(os.popen('stty size', 'r').read().split()[1])
            start_chars = "Progress: "
            end_chars = "   "
            full_squares = int(val * 0.01 * (columns - len(start_chars) - len(end_chars)))
            empty_squares = columns - len(start_chars) - len(end_chars) - full_squares
            if val < 100:
                print(start_chars + "■"*full_squares + "□"*empty_squares + end_chars, end="\r")
            else:
                print(start_chars + "■"*full_squares + "□"*empty_squares + end_chars, end="")
        except IndexError:
            if val < 100:
                print("{}% complete".format(val), end="\r")
            else:
                print("{}% complete".format(val), end="")
