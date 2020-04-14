"""tarstall: A package manager for managing archives
    Copyright (C) 2020  hammy3502

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

import os
from shutil import copyfile, rmtree, move, which, copy, copytree
from subprocess import call, run, DEVNULL, PIPE
import sys
import re
import getpass

try:
    import requests
    can_update = True
except ImportError:
    can_update = False
    print("##########WARNING##########")
    print("requests library not installed! Ability to update tarstall")
    print("has been disabled! Use `pip3 install requests` or ")
    print("`python3 -m pip install requests` to install it!")
    print("###########################")

import config
import generic

if config.verbose:
    c_out = None
else:
    c_out = DEVNULL

def add_upgrade_url(program, url):
    """Adds an Upgrade URL to a Program.

    Args:
        program (str): The program that will be upgraded
        url (str): The URL containing the archive to upgrade from. THIS MUST BE A VALID URL!!!!!

    """
    config.db["programs"][program]["update_url"] = url
    config.write_db()


def remove_update_url(program):
    """Removes Upgrade URL for Program.

    Args:
        program (str): Program to remove URL of.

    """
    config.db["programs"][program]["update_url"] = None
    config.write_db()


def wget_program(program):
    """Wget an Archive and Overwrite Program.

    Args:
        program (str): Program that has an update_url to update

    Returns:
        str: "No wget", "Wget error", "Install error" if install() fails, "Success" on success.

    """
    if not config.check_bin("wget"):
        return "No wget"
    else:
        config.vprint("Creating second temp folder for archive.")
        try:
            rmtree(config.full("/tmp/tarstall-temp2"))
        except FileNotFoundError:
            pass
        os.mkdir("/tmp/tarstall-temp2")
        os.chdir("/tmp/tarstall-temp2")
        config.vprint("Downloading archive...")
        url = config.db["programs"][program]["update_url"]
        if config.verbose:
            err = call(["wget", url])
        else:
            err = call(["wget", url], stdout=DEVNULL, stderr=DEVNULL)
        if err != 0:
            return "Wget error"
        files = os.listdir()
        config.vprint("Renaming archive")
        os.rename("/tmp/tarstall-temp2/{}".format(files[0]), "/tmp/tarstall-temp2/{}".format(program + ".tar.gz"))
        os.chdir("/tmp/")
        config.vprint("Using install to install the program.")
        inst_status = pre_install("/tmp/tarstall-temp2/{}".format(program + ".tar.gz"), True, show_progress=False)
        try:
            rmtree(config.full("/tmp/tarstall-temp2"))
        except FileNotFoundError:
            pass
        if inst_status != "Installed":
            return "Install error"
        else:
            return "Success"


def update_program(program):
    """Update Program.

    Args:
        program (str): Name of program to update

    Returns:
        str: "No script" if script doesn't exist, "Script error" if script
        failed to execute, or "Success" on a success. Can also be something
        from update_git_program if the program supplied is a
        git installed program. Can also return "OSError" if the supplied
        script doesn't specify the shell to be used. Can also return
        something from wget_program().

    """
    if config.db["programs"][program]["git_installed"]:
        status = update_git_program(program)
        if config.db["programs"][program]["post_upgrade_script"] is None:
            return status
        elif status != "Success":
            return status
    if config.db["programs"][program]["update_url"] is not None:
        status = wget_program(program)
        if config.db["programs"][program]["post_upgrade_script"] is None:
            return status
        elif status != "Success":
            return status
    if config.db["programs"][program]["post_upgrade_script"] is not None:
        if not config.db["programs"][program]["post_upgrade_script"]:
            config.db["programs"][program]["post_upgrade_script"] = None
            config.write_db()
            return "No script"
        else:
            try:
                err = call(config.db["programs"][program]["post_upgrade_script"], 
                cwd=config.full("~/.tarstall/bin/{}".format(program)), stdout=c_out)
                if err != 0:
                    return "Script error"
                else:
                    return "Success"
            except OSError:
                return "OSError"


def update_script(program, script_path):
    """Set Update Script.

    Set a script to run when a program is updated.

    Args:
        program (str): Program to set an update script for
        script_path (str): Path to script to run as an/after update.

    Returns:
        str: "Bad path" if the path doesn't exist, "Success" on success, and "Wiped" on clear.

    """
    if script_path == "":
        config.db["programs"][program]["post_upgrade_script"] = None
        return "Wiped"
    if not config.exists(config.full(script_path)):
        return "Bad path"
    config.db["programs"][program]["post_upgrade_script"] = config.full(script_path)
    config.write_db()
    return "Success"


def update_git_program(program):
    """Update Git Program.

    Args:
        program (str): Name of program to update

    Returns:
        str: "No git" if git isn't found, "Error updating" on a generic failure, "Success" on a successful update, and
        "No update" if the program is already up-to-date.

    """
    if not config.check_bin("git"):
        config.vprint("git isn't installed!")
        return "No git"
    outp = run(["git", "pull"], cwd=config.full("~/.tarstall/bin/{}".format(program)), stdout=PIPE, stderr=PIPE)
    err = outp.returncode
    output = str(outp.stdout) + "\n\n\n" + str(outp.stderr)
    if err != 0:
        config.vprint("Failed updating: {}".format(program))
        return "Error updating"
    else:
        if "Already up to date." in output:
            config.vprint("{} is already up to date!".format(program))
            return "No update"
        else:
            config.vprint("Successfully updated: {}".format(program))
            return "Success"


def update_programs():
    """Update Programs Installed through Git or Ones with Upgrade Scripts.

    Returns:
        str/dict: "No git" if git isn't installed, or a dict containing program names and results from update_git_program()
        It can also return "No programs" if no programs are installed.

    """
    if len(config.db["programs"].keys()) == 0:
        return "No programs"
    if not config.check_bin("git"):
        return "No git"
    increment = int(100 / len(config.db["programs"].keys()))
    progress = 0
    statuses = {}
    generic.progress(progress)
    for p in config.db["programs"].keys():
        if not config.db["programs"][p]["update_url"] and (config.db["programs"][p]["git_installed"] or config.db["programs"][p]["post_upgrade_script"]):
            statuses[p] = update_program(p)
        elif (config.db["programs"][p]["update_url"] and config.read_config("UpdateURLPrograms")):
            statuses[p] = update_program(p)
        progress += increment
        generic.progress(progress)
    if progress < 100:
        generic.progress(100)
    return statuses


def change_git_branch(program, branch):
    """Change Git Program's Branch.

    Args:
        program (str): Program to change the git branch of
        branch (str): Branch to change to

    Returns:
        str: "No git", "Error changing", or "Success"

    """
    if not config.check_bin("git"):
        return "No git"
    err = call(["git", "checkout", "-f", branch], cwd=config.full("~/.tarstall/bin/{}".format(program)), stdout=c_out)
    if err != 0:
        return "Error changing"
    else:
        return "Success"


def change_branch(branch, reset=False):
    """Change Branch.

    Args:
        branch (str): Branch to change to (master or beta)
        reset (bool): If changing to stable, whether or not to reset tarstall. Defaults to False.

    Returns:
        str: "Bad branch" if switching to an invalid branch, "Success" on master --> beta,
        "Reset" if beta --> master and reset is complete, or "Waiting" if beta --> master
        without doing the reset.

    """
    if branch == "master":
        if not config.check_bin("git"):
            reset = False
            generic.progress(50)
    if branch not in ["master", "beta"]:
        return "Bad branch"
    config.vprint("Switching branch and writing change to file")
    config.db["version"]["branch"] = branch
    config.branch = branch
    config.write_db()
    if branch == "beta":
        config.vprint("Updating tarstall...")
        generic.progress(65)
        update()
        return "Success"
    elif branch == "master":
        generic.progress(10)
        if reset:
            config.vprint("Resetting by forcing an update of tarstall.")
            update(True, False)
            generic.progress(70)
            config.vprint("Deleting old .desktops")
            for prog in config.db["programs"]:
                if config.db["programs"][prog]["desktops"]:
                    for d in config.db["programs"][prog]["desktops"]:
                        try:
                            os.remove(config.full("~/.local/share/applications/{}.desktop".format(d)))
                        except FileNotFoundError:
                            pass
            generic.progress(85)
            config.vprint("Writing 'refresh' key to database to tell tarstall to reset itself")
            config.db = {"refresh": True}
            config.write_db()
            generic.progress(100)
            config.unlock()
            config.vprint("Done!")
            return "Reset"
        else:
            generic.progress(100)
            return "Waiting"


def tarstall_startup(start_fts=False, del_lock=False, old_upgrade=False):
    """Run on Startup.

    Runs on tarstall startup to perform any required checks and upgrades.
    This function should always be run before doing anything else with tarstall.

    Args:
        start_fts (bool): Whether or not to start first time setup
        del_lock (bool): Whether or not to remove the lock (if it exists)

    Returns:
        str: One of many different values indicating the status of tarstall. Those include:
        "Not installed", "Locked", "Good" (nothing bad happened), "Root", "Old" (happens
        when upgrading from tarstall prog_version 1), and "Unlocked" if tarstall 
        was successfully unlocked. Can also return a string from first_time_setup.

    """
    if config.locked():  # Lock check
        config.vprint("Lock file detected at /tmp/tarstall-lock.")
        if del_lock:
            config.vprint("Deleting the lock and continuing execution!")
            config.unlock()
            return "Unlocked"
        else:
            config.vprint("Lock file removal not specified; staying locked.")
            return "Locked"
    else:
        config.lock()

    if config.db == {"refresh": True}:  # Downgrade check
        print("Hang tight! We're finishing up your downgrade...")
        generic.progress(5)
        config.create("~/.tarstall/database")
        create_db()
        generic.progress(15)
        config.db = config.get_db()
        config.write_db()
        generic.progress(20)
        rmtree(config.full("~/.tarstall/bin"))
        generic.progress(90)
        os.mkdir(config.full("~/.tarstall/bin"))
        generic.progress(100)
        print("We're done! Continuing tarstall execution...")

    if start_fts:  # Check if -f or --first is supplied
        return first_time_setup()

    if not(config.exists('~/.tarstall/tarstall_execs/tarstall')):  # Make sure tarstall is installed
        return "Not installed"

    file_version = get_file_version('file')
    while config.get_version('file_version') > file_version:  # Lingering upgrades check
        config.vprint("Upgrading files and database from {} to {}.".format(file_version, config.get_version("file_version")))

        if file_version == 11:
            config.vprint("Adding 'update_url' key in database for all programs!")
            for program in config.db["programs"]:
                config.db["programs"][program]["update_url"] = None
        
        elif file_version == 12:
            config.vprint("Adding 'has_path' and 'binlinks' to programs.")
            for program in config.db["programs"]:
                config.db["programs"][program]["has_path"] = False
                config.db["programs"][program]["binlinks"] = []
        
        elif file_version == 13:
            config.vprint("Adding 'UpdateURLPrograms' to config database.")
            config.db["options"]["UpdateURLPrograms"] = False

        config.db["version"]["file_version"] += 1
        file_version = get_file_version('file')
        config.write_db()

    if get_file_version('prog') == 1:  # Online update broke between prog versions 1 and 2 of tarstall
        return "Old"

    if config.read_config("AutoInstall"):  # Auto-update, if enabled
        update(show_progress=False)
    
    username = getpass.getuser()  # Root check
    if username == 'root':
        config.vprint("We're running as root!")
        return "Root"
    
    return "Good"


def pre_install(program, overwrite=None, show_progress=True):
    """Pre-Archive Install.

    Preparation before installing an archive.

    Arguments:
        program (str): Path to archive to attempt installation.
        overwrite (bool/None): Whether or not to overwrite the program if it exists.

    Returns:
        str: Status of the installation. Possible returns are: "Bad file", and "Application exists".

    """
    if not config.exists(program):
        return "Bad file"
    program_internal_name = config.name(program)  # Get the program name
    if program_internal_name in config.db["programs"]:  # Reinstall check
        if overwrite is None:
            return "Application exists"
        else:
            if not overwrite:
                uninstall(program_internal_name)
                return install(program, False, True, show_progress)  # Reinstall
            elif overwrite:
                return install(program, True, True, show_progress)
    else:
        return install(program, show_progress=show_progress)  # No reinstall needed to be asked, install program
    config.write_db()


def pre_gitinstall(program, overwrite=None):
    """Before Git Installs.

    Args:
        program (str): Git URL to install
        overwrite (bool/None): Whether to do an overwrite reinstall. Defaults to None.

    Returns:
        str: Statuses. Includes: 

    """
    if not config.check_bin("git"):
        return "No git"
    elif re.match(r"https://\w.\w", program) is None or " " in program or "\\" in program or config.extension(program) != ".git":
        return "Bad URL"
    else:
        program_internal_name = config.name(program)
        if program_internal_name in config.db["programs"]:
            if overwrite is None:
                return "Application exists"
            else:
                if not overwrite:
                    uninstall(program_internal_name)
                    return gitinstall(program, program_internal_name, False, True)
                elif overwrite:
                    return gitinstall(program, program_internal_name, True, True)
        else:
            return gitinstall(program, program_internal_name)
    config.write_db()


def pre_dirinstall(program, overwrite=None):
    if not(os.path.isdir(config.full(program))) or program[-1:] != '/':
        return "Bad folder"
    program_internal_name = config.dirname(program)
    if program_internal_name in config.db["programs"]:
        if overwrite is None:
            return "Application exists"
        elif not overwrite:
            uninstall(program_internal_name)
            return dirinstall(program, program_internal_name, False, True)
        elif overwrite:
            return dirinstall(program, program_internal_name, True, True)
    else:
        return dirinstall(program, program_internal_name)
    config.write_db()


def create_db():
    """Creates Database."""
    db_template = {
        "options": {
            "Verbose": False,
            "AutoInstall": False,
            "ShellFile": config.get_shell_file(),
            "SkipQuestions": False,
            "UpdateURLPrograms": False
        },
        "version": {
            "file_version": config.file_version,
            "prog_internal_version": config.prog_internal_version,
            "branch": "master"
        },
        "programs": {
        }
    }
    config.db = db_template
    config.write_db()


def remove_desktop(program, desktop):
    """Remove .desktop

    Removes a .desktop file assosciated with a program and its corresponding entry in the database
    This process is walked through with the end-user

    Args:
        program (str): Program to remove
        desktop (str): Name of .desktop to remove

    """
    try:
        os.remove(config.full("~/.local/share/applications/{}.desktop".format(desktop)))
    except FileNotFoundError:
        pass
    config.db["programs"][program]["desktops"].remove(desktop)
    config.write_db()


def remove_paths_and_binlinks(program):
    """Remove PATHs and binlinks for "program"

    Args:
        program (str): Program to remove PATHs and binlinks of

    Returns:
        str: "Complete"

    """
    config.remove_line(program, "~/.tarstall/.bashrc", 'poundword')
    config.db["programs"][program]["has_path"] = False
    config.db["programs"][program]["binlinks"] = []
    config.write_db()
    return "Complete"


def rename(program, new_name):
    """Rename Program.

    Args:
        program (str): Name of program to rename

    Returns:
        str/None: New program name or None if program already exists

    """
    if new_name in config.db["programs"]:
        return None
    for d in config.db["programs"][program]["desktops"]:
        config.replace_in_file("/.tarstall/bin/{}".format(program), "/.tarstall/bin/{}".format(new_name), 
        "~/.local/share/applications/{}.desktop".format(d))
    generic.progress(25)
    config.db["programs"][new_name] = config.db["programs"].pop(program)
    config.replace_in_file("export PATH=$PATH:~/.tarstall/bin/" + program, 
    "export PATH=$PATH:~/.tarstall/bin/" + new_name, "~/.tarstall/.bashrc")
    generic.progress(50)
    config.replace_in_file("'cd " + config.full('~/.tarstall/bin/' + program),
    "'cd " + config.full('~/.tarstall/bin/' + new_name), "~/.tarstall/.bashrc")
    generic.progress(75)
    config.replace_in_file("# " + program, "# " + new_name, "~/.tarstall/.bashrc")
    move(config.full("~/.tarstall/bin/" + program), config.full("~/.tarstall/bin/" + new_name))
    config.write_db()
    generic.progress(100)
    return new_name


def finish_install(program_internal_name, is_git=False):
    """End of Install.

    Ran after every program install.

    Args:
        program_internal_name (str): Name of program as stored in the database

    Returns:
        str: "Installed".

    """
    generic.progress(90)
    config.vprint("Removing temporary install directory (if it exists)")
    try:
        rmtree("/tmp/tarstall-temp")
    except FileNotFoundError:
        pass
    config.vprint("Adding program to tarstall list of programs")
    generic.progress(95)
    config.db["programs"].update({program_internal_name: {"git_installed": is_git, "desktops": [], 
    "post_upgrade_script": None, "update_url": None, "has_path": False, "binlinks": []}})
    config.write_db()
    generic.progress(100)
    return "Installed"


def create_desktop(program_internal_name, name, program_file, comment="", should_terminal="", cats=[], icon="", path=""):
    """Create Desktop.

    Create a desktop file for a program installed through tarstall.

    Args:
        program_internal_name (str/None): Name of program or None if not a tarstall program.
        name (str): The name as will be used in the .desktop file
        program_file (str): The file in the program directory to point the .desktop to, or the path to it if program_internal_name is None
        comment (str): The comment as to be displayed in the .desktop file
        should_terminal (str): "True" or "False" as to whether or not a terminal should be shown on program run
        cats (str[]): List of categories to put in .desktop file
        icon (str): The path to a valid icon or a specified icon as would be put in a .desktop file
        path (str): The path to where the .desktop should be run. Only used when program_internal_name is None.

    Returns:
        str: "Already exists" if the .desktop file already exists or "Created" if the desktop file was
        successfully created.

    """
    if program_internal_name is not None:
        exec_path = config.full("~/.tarstall/bin/{}/{}".format(program_internal_name, program_file))
        path = config.full("~/.tarstall/bin/{}/".format(program_internal_name))
        file_name = program_file
        if "/" in file_name:
            file_name += ".tar.gz"
            file_name = config.name(file_name)
        desktop_name = "{}-{}".format(file_name, program_internal_name)
    else:
        exec_path = config.full(program_file)
        desktop_name = name
        path = config.full(path)
    if config.exists("~/.local/share/applications/{}.desktop".format(desktop_name)):
        print("Desktop file already exists!")
        return "Already exists"
    if "Video" in cats or "Audio" in cats and "AudioVideo" not in cats:
        cats.append("AudioVideo")
    if not cats:
        cats = ["Utility"]
    cats = ";".join(cats) + ";"  # Get categories for the .desktop
    if comment != "":
        comment = "Comment=" + comment
    if icon != "":
        icon = "Icon=" + icon
    to_write = """
[Desktop Entry]
Name={name}
{comment}
Path={path}
Exec={exec_path}
{icon}
Terminal={should_terminal}
Type=Application
Categories={categories}
""".format(name=name, comment=comment, exec_path=exec_path,
           should_terminal=should_terminal, categories=cats,
           icon=icon, path=path)
    os.chdir(config.full("~/.local/share/applications/"))
    config.create("./{}.desktop".format(desktop_name))
    with open(config.full("./{}.desktop".format(desktop_name)), 'w') as f:
        f.write(to_write)
    if program_internal_name is not None:
        config.db["programs"][program_internal_name]["desktops"].append(desktop_name)
        config.write_db()
    return "Created"


def gitinstall(git_url, program_internal_name, overwrite=False, reinstall=False):
    """Git Install.

    Installs a program from a URL to a Git repository

    Args:
        git_url (str): URL to Git repository
        program_internal_name (str): Name of program to use
        overwrite (bool): Whether or not to assume the program is already installed and to overwite it

    Returns:
       str: A string from finish_install(), "No rsync", "Installed", or "Error"

    """
    if not config.check_bin("rsync") and overwrite:
        return "No rsync"
    config.vprint("Downloading git repository")
    if overwrite:
        try:
            rmtree(config.full("/tmp/tarstall-temp"))  # Removes temp directory (used during installs)
        except FileNotFoundError:
            pass
        os.mkdir("/tmp/tarstall-temp")
        os.chdir("/tmp/tarstall-temp")
    else:
        os.chdir(config.full("~/.tarstall/bin"))
    generic.progress(5)
    if config.verbose:
        err = call(["git", "clone", git_url])
    else:
        err = call(["git", "clone", git_url], stderr=DEVNULL)
    if err != 0:
        return "Error"
    generic.progress(65)
    if overwrite:
        call(["rsync", "-a", "/tmp/tarstall-temp/{}/".format(program_internal_name), config.full("~/.tarstall/bin/{}".format(program_internal_name))], stdout=c_out)
    if not overwrite:
        return finish_install(program_internal_name, True)
    else:
        generic.progress(100)
        return "Installed"


def add_binlink(file_chosen, program_internal_name):
    """Add Binlink.

    Args:
        file_chosen (str): File to add
        program_internal_name (str): Name of program to binlink

    Returns:
        str: "Added" or "Already there"

    """
    name = file_chosen
    if "/" in name:
        name += ".tar.gz"
        name = config.name(name)
    if name in config.db["programs"][program_internal_name]["binlinks"]:
        return "Already there"
    line_to_add = '\nalias ' + name + "='cd " + config.full('~/.tarstall/bin/' + program_internal_name) + \
    '/ && ./' + file_chosen + "' # " + program_internal_name
    config.vprint("Adding alias to bashrc")
    config.add_line(line_to_add, "~/.tarstall/.bashrc")
    config.db["programs"][program_internal_name]["binlinks"].append(name)
    config.write_db()
    return "Added"


def pathify(program_internal_name):
    """Add Program to Path.

    Adds a program to PATH through ~/.tarstall/.bashrc

    Args:
        program_internal_name (str): Name of program to add to PATH

    Returns:
        "Complete" or "Already there"

    """
    if config.db["programs"][program_internal_name]["has_path"]:
        return "Already there"
    config.vprint('Adding program to PATH')
    line_to_write = "\nexport PATH=$PATH:~/.tarstall/bin/" + program_internal_name + ' # ' + program_internal_name
    config.add_line(line_to_write, "~/.tarstall/.bashrc")
    config.db["programs"][program_internal_name]["has_path"] = True
    return "Complete"


def update(force_update=False, show_progress=True):
    """Update tarstall.

    Checks to see if we should update tarstall, then does so if one is available

    Returns:
        str: "No requests" if requests isn't installed, "No internet if there isn't
        an internet connection, "Newer version" if the installed
        version is newer than the one online, "No update" if there is no update,
        "Updated" upon a successful update, "No git" if git isn't installed,
        or "Failed" if it failed.

    """
    if not can_update:
        config.vprint("requests isn't installed.")
        return "No requests"
    elif not config.check_bin("git"):
        config.vprint("git isn't installed.")
        return "No git"
    generic.progress(5, show_progress)
    prog_version_internal = config.get_version('prog_internal_version')
    config.vprint("Checking version on GitHub")
    final_version = get_online_version('prog')
    if not force_update:
        if final_version == -1:
            generic.progress(100, show_progress)
            return "No requests"
        elif final_version == -2:
            generic.progress(100, show_progress)
            return "No internet"
        config.vprint('Installed internal version: ' + str(prog_version_internal))
        config.vprint('Version on GitHub: ' + str(final_version))
    generic.progress(10, show_progress)
    if force_update or final_version > prog_version_internal:
        try:
            rmtree("/tmp/tarstall-update")
        except FileNotFoundError:
            pass
        os.chdir("/tmp/")
        os.mkdir("tarstall-update")
        os.chdir("/tmp/tarstall-update")
        config.vprint("Cloning tarstall repository from git")
        if config.verbose:
            err = call(["git", "clone", "--branch", config.branch, "https://github.com/hammy3502/tarstall.git"])
        else:
            err = call(["git", "clone", "--branch", config.branch, "https://github.com/hammy3502/tarstall.git"], stderr=c_out)
        if err != 0:
            generic.progress(100, show_progress)
            return "Failed"
        generic.progress(55, show_progress)
        config.vprint("Removing old tarstall files")
        os.chdir(config.full("~/.tarstall/"))
        files = os.listdir()
        to_keep = ["bin", "database", ".bashrc"]
        for f in files:
            if f not in to_keep:
                if os.path.isdir(config.full("~/.tarstall/{}".format(f))):
                    rmtree(config.full("~/.tarstall/{}".format(f)))
                else:
                    os.remove(config.full("~/.tarstall/{}".format(f)))
        generic.progress(70, show_progress)
        config.vprint("Moving in new tarstall files")
        os.chdir("/tmp/tarstall-update/tarstall/")
        files = os.listdir()
        to_ignore = [".git", ".gitignore", "README.md", "readme-images", "COPYING", "requirements.txt", "requirements-gui.txt", "tests", "install_tarstall"]
        for f in files:
            if f not in to_ignore:
                move("/tmp/tarstall-update/tarstall/{}".format(f), config.full("~/.tarstall/{}".format(f)))
        generic.progress(85, show_progress)
        config.vprint("Removing old tarstall temp directory")
        os.chdir(config.full("~/.tarstall/"))
        try:
            rmtree("/tmp/tarstall-update")
        except FileNotFoundError:
            pass
        config.db["version"]["prog_internal_version"] = final_version
        config.write_db()
        generic.progress(100, show_progress)
        return "Updated"
    elif final_version < prog_version_internal:
        generic.progress(100, show_progress)
        return "Newer version"
    else:
        generic.progress(100, show_progress)
        return "No update"


def erase():
    """Remove tarstall.

    Returns:
        str: "Erased" on success, "Not installed" if tarstall isn't installed, or "No line" if the shell
        line couldn't be removed.

    """
    if not (config.exists(config.full("~/.tarstall/tarstall_execs/tarstall"))):
        return "Not installed"
    config.vprint('Removing source line from bashrc')
    try:
        config.remove_line("~/.tarstall/.bashrc", "~/{}".format(config.read_config("ShellFile")), "word")
        to_return = "Erased"
    except FileNotFoundError:
        to_return = "No line"
    generic.progress(10)
    config.vprint("Removing .desktop files")
    for prog in config.db["programs"]:
        if config.db["programs"][prog]["desktops"]:
            for d in config.db["programs"][prog]["desktops"]:
                try:
                    os.remove(config.full("~/.local/share/applications/{}.desktop".format(d)))
                except FileNotFoundError:
                    pass
    generic.progress(40)
    config.vprint('Removing tarstall directory')
    rmtree(config.full('~/.tarstall'))
    generic.progress(90)
    try:
        rmtree("/tmp/tarstall-temp")
    except FileNotFoundError:
        pass
    generic.progress(95)
    try:
        rmtree("/tmp/tarstall-temp2")
    except FileNotFoundError:
        pass
    generic.progress(98)
    try:
        os.remove(config.full("~/.local/share/applications/tarstall.desktop"))
    except FileNotFoundError:
        pass
    config.unlock()
    generic.progress(100)
    return to_return


def first_time_setup():
    """First Time Setup.

    Sets up tarstall for the first time.

    Returns:
        str: "Already installed" if already installed, "Success" on installation success, "Unsupported shell"
        on success but the shell being used isn't supported.

    """
    os.chdir(os.path.dirname(__file__))
    if config.exists(config.full('~/.tarstall/tarstall_execs/tarstall')):
        return "Already installed"
    print('Installing tarstall to your system...')
    generic.progress(5)
    try:
        os.mkdir(config.full("~/.tarstall"))
    except FileExistsError:
        rmtree(config.full("~/.tarstall"))
        os.mkdir(config.full("~/.tarstall"))
    try:
        os.mkdir(config.full("/tmp/tarstall-temp/"))
    except FileExistsError:
        rmtree(config.full("/tmp/tarstall-temp"))
        os.mkdir(config.full("/tmp/tarstall-temp/"))
    generic.progress(10)
    os.mkdir(config.full("~/.tarstall/bin"))
    config.create("~/.tarstall/database")
    create_db()
    config.create("~/.tarstall/.bashrc")  # Create directories and files
    generic.progress(15)
    progress = 15
    files = os.listdir()
    prog_change = int(55 / len(files))
    for i in files:
        i_num = len(i) - 3
        if i[i_num:len(i)] == '.py':
            try:
                copyfile(i, config.full('~/.tarstall/' + i))
            except FileNotFoundError:
                return "Bad copy"
        progress += prog_change
        generic.progress(progress)
    generic.progress(70)
    shell_file = config.read_config("ShellFile")
    if shell_file is None:
        to_return = "Unsupported shell"
    else:
        to_return = "Success"
        config.add_line("source ~/.tarstall/.bashrc\n", "~/{}".format(shell_file))
    generic.progress(75)
    copytree(config.full("./tarstall_execs/"), config.full("~/.tarstall/tarstall_execs/"))  # Move tarstall.py to execs dir
    generic.progress(90)
    if not config.exists("~/.local/share/applications"):
        os.mkdir(config.full("~/.local/share/applications"))
    generic.progress(92)
    config.add_line("export PATH=$PATH:{}".format(
                config.full("~/.tarstall/tarstall_execs")), "~/.tarstall/.bashrc")  # Add bashrc line
    generic.progress(95)
    os.system('sh -c "chmod +x ~/.tarstall/tarstall_execs/tarstall"')
    config.unlock()
    generic.progress(100)
    return to_return


def verbose_toggle():
    """Enable/Disable Verbosity.

    Returns:
        str: "enabled"/"disabled", depending on the new state.

    """
    new_value = config.change_config('Verbose', 'flip')
    return generic.endi(new_value)


def create_command(file_extension, program):
    """Create Extraction Command.

    Args:
        file_extension (str): File extension of program (including .)
        program (str): Program name
        overwrite_files (bool): Whether or not the command should overwrite files. Defaults to False.

    Returns:
        str: Command to run, "Bad Filetype", or "No bin_that_is_needed"

    """
    if config.vcheck():  # Creates the command to run to extract the archive
        if file_extension == '.tar.gz' or file_extension == '.tar.xz':
            vflag = 'v'
        elif file_extension == '.zip':
            vflag = ''
        elif file_extension == '.7z':
            vflag = ''
        elif file_extension == '.rar':
            vflag = ''
    else:
        if file_extension == '.tar.gz' or file_extension == '.tar.xz':
            vflag = ''
        elif file_extension == '.zip':
            vflag = '-qq'
        elif file_extension == '.7z':
            vflag = '-bb0 -bso0 -bd '
        elif file_extension == '.rar':
            vflag = '-idcdpq '
    if file_extension == '.tar.gz' or file_extension == '.tar.xz':
        command_to_go = "tar " + vflag + "xf " + program + " -C /tmp/tarstall-temp/"
        if which("tar") is None:
            print("tar not installed; please install it to install .tar.gz and .tar.xz files!")
            return "No tar"
    elif file_extension == '.zip':
        command_to_go = 'unzip ' + vflag + ' ' + program + ' -d /tmp/tarstall-temp/'
        if which("unzip") is None:
            print("unzip not installed; please install it to install ZIP files!")
            return "No unzip"
    elif file_extension == '.7z':
        command_to_go = '7z x ' + vflag + program + ' -o/tmp/tarstall-temp/'
        if which("7z") is None:
            return "No 7z"
    elif file_extension == '.rar':
        command_to_go = 'unrar x ' + vflag + program + ' /tmp/tarstall-temp/'
        if which("unrar") is None:
            return "No unrar"
    else:
        print('Error! File type not supported!')
        return "Bad Filetype"
    config.vprint("Running command: " + command_to_go)
    return command_to_go


def install(program, overwrite=False, reinstall=False, show_progress=True):
    """Install Archive.

    Takes an archive and installs it.

    Args:
        program (str): Path to archive to install
        overwrite (bool): Whether or not to assume the program is already installed and to overwite it

    Returns:
       str: A string from finish_install() a string from create_command(), "No rsync", "Bad name", "Installed", or "Error".

    """
    if not config.check_bin("rsync") and overwrite:
        return "No rsync"
    program_internal_name = config.name(program)
    if config.char_check(program_internal_name):
        return "Bad name"
    config.vprint("Removing old temp directory (if it exists!)")
    try:
        rmtree(config.full("/tmp/tarstall-temp"))  # Removes temp directory (used during installs)
    except FileNotFoundError:
        pass
    generic.progress(10, show_progress)
    config.vprint("Creating new temp directory")
    os.mkdir(config.full("/tmp/tarstall-temp"))  # Creates temp directory for extracting archive
    config.vprint("Extracting archive to temp directory")
    file_extension = config.extension(program)
    program = config.spaceify(program)
    command_to_go = create_command(file_extension, program)
    config.vprint('File type detected: ' + file_extension)
    generic.progress(15, show_progress)
    if command_to_go.startswith("No") or command_to_go == "Bad Filetype":
        return command_to_go
    try:
        os.system(command_to_go)  # Extracts program archive
    except:
        print('Failed to run command: ' + command_to_go + "!")
        print("Program installation halted!")
        return "Error"
    generic.progress(50, show_progress)
    config.vprint('Checking for folder in folder')
    os.chdir("/tmp/tarstall-temp/")
    if os.path.isdir(config.full('/tmp/tarstall-temp/' + program_internal_name + '/')):
        config.vprint('Folder in folder detected! Using that directory instead...')
        source = config.full('/tmp/tarstall-temp/' + program_internal_name) + '/'
        dest = config.full('~/.tarstall/bin/' + program_internal_name) + '/'
    elif len(os.listdir()) == 1 and os.path.isdir(os.listdir()[0]):
        config.vprint("Single folder detected!")
        folder = os.listdir()[0]
        source = config.full("/tmp/tarstall-temp/" + folder) + '/'
        dest = config.full("~/.tarstall/bin/" + program_internal_name) + '/'
    else:
        config.vprint('Folder in folder not detected!')
        source = config.full('/tmp/tarstall-temp') + '/'
        dest = config.full('~/.tarstall/bin/' + program_internal_name) + '/'
    config.vprint("Moving program to directory")
    if overwrite:
        if verbose:
            verbose_flag = "v"
        else:
            verbose_flag = ""
        call(["rsync", "-a{}".format(verbose_flag), source, dest], stdout=c_out)
    else:
        move(source, dest)
    generic.progress(80, show_progress)
    config.vprint("Adding program to tarstall list of programs")
    config.vprint('Removing old temp directory...')
    os.chdir("/tmp")
    try:
        rmtree(config.full("/tmp/tarstall-temp"))
    except FileNotFoundError:
        config.vprint('Temp folder not found so not deleted!')
    if not reinstall:
        return finish_install(program_internal_name)
    else:
        generic.progress(100, show_progress)
        return "Installed"


def dirinstall(program_path, program_internal_name, overwrite=False, reinstall=False):
    """Install Directory.

    Installs a directory as a program

    Args:
        program_path (str): Path to directory to install
        program_internal_name (str): Name of program
        overwrite (bool): Whether or not to assume the program is already installed and to overwite it

    Returns:
       str: A string from finish_install(), "Installed", or "No rsync"

    """
    generic.progress(10)
    if not config.check_bin("rsync") and overwrite:
        return "No rsync"
    config.vprint("Moving folder to tarstall destination")
    if overwrite:
        call(["rsync", "-a", program_path, config.full("~/.tarstall/bin/{}".format(program_internal_name))], stdout=c_out)
        rmtree(program_path)
    else:
        move(program_path, config.full("~/.tarstall/bin/"))
    if not reinstall:
        return finish_install(program_internal_name)
    else:
        return "Installed"


def uninstall(program):
    """Uninstall a Program.

    Args:
        program (str): Name of program to uninstall

    Returns:
        str: Status detailing the uninstall. Can be: "Not installed" or "Success".

    """
    if not program in config.db["programs"]:
        return "Not installed"
    config.vprint("Removing program files")
    rmtree(config.full("~/.tarstall/bin/" + program + '/'))
    generic.progress(20)
    config.vprint("Removing program from PATH and any binlinks for the program")
    config.remove_line(program, "~/.tarstall/.bashrc", 'poundword')
    generic.progress(30)
    config.vprint("Removing program desktop files")
    if config.db["programs"][program]["desktops"]:
        for d in config.db["programs"][program]["desktops"]:
            try:
                os.remove(config.full("~/.local/share/applications/{}.desktop".format(d)))
            except FileNotFoundError:
                pass
    generic.progress(80)
    config.vprint("Removing program from tarstall list of programs")
    del config.db["programs"][program]
    config.write_db()
    generic.progress(100)
    return "Success"


def list_programs():
    """List Installed Programs.

    Returns:
        str[]: List of installed programs by name
    
    """
    return list(config.db["programs"].keys())


def get_online_version(type_of_replacement, branch=config.branch):
    """Get tarstall Version from GitHub.

    Args:
        type_of_replacement (str): Type of version to get (file or prog)
        branch (str): Branch to check version of (default: User's current branch)
    
    Returns:
        int: The specified version, -1 if requests is missing, or -2 if not connected to the internet.
    """
    if not can_update:
        print("requests library not installed! Exiting...")
        return -1
    version_url = "https://raw.githubusercontent.com/hammy3502/tarstall/{}/version".format(branch)
    try:
        version_raw = requests.get(version_url)
    except requests.ConnectionError:
        return -2
    version = version_raw.text
    spot = version.find(".")
    if type_of_replacement == 'file':
        return int(version[0:spot])
    elif type_of_replacement == 'prog':
        return int(version[spot + 1:])


def get_file_version(version_type):
    """Get Database Versions.

    Gets specified version of tarstall as stored in the database

    Args:
        version_type (str): Type of version to look up (file/prog)

    Returns:
        int: The specified version number

    """
    if version_type == 'file':
        return config.db["version"]["file_version"]
    elif version_type == 'prog':
        return config.db["version"]["prog_internal_version"]


verbose = config.vcheck()
