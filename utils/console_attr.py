# utils/console_attr.py

from enum import Enum

from colorama import Fore, Style
from colorama import init as colorama_init

class ConsoleAttr(Enum):
    SUCCESS = "success"
    INFO = "info"
    ERROR = "error"

def console_print(msg, attr) -> None:
    """Prints a message to the console its attribute: success, info or error.

    This function prints a message to the console with color attributes. The
    message is printed in the specified color and the color attributes are reset
    at the end of the message.

    Args:
        msg (str): Message to print.
        attr (str): success, info or error.

    Example:
        >>> console_print("Hello, World!", success)
    """
    if attr == ConsoleAttr.SUCCESS:
        print(f"{Fore.LIGHTGREEN_EX}{msg}{Style.RESET_ALL}")
    elif attr == ConsoleAttr.INFO:
        print(f"{Fore.LIGHTBLUE_EX}{msg}{Style.RESET_ALL}")
    elif attr == ConsoleAttr.ERROR:
        print(f"{Fore.LIGHTRED_EX}{msg}{Style.RESET_ALL}")

