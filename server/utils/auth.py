import yaml
from rich.prompt import Confirm, Prompt

def authorize(action: str) -> tuple[bool, str | None]:
    """
    Checks if a given action requires user authorization and, if so, prompts the user for it.

    Args:
        action: The name of the action to authorize.

    Returns:
        A tuple containing a boolean indicating whether the action is authorized,
        and an optional string with the reason for denial.
    """
    with open("../server_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    if config.get("approval_required", {}).get(action):
        is_authorized = Confirm.ask(f"Do you want to authorize the action: [bold cyan]{action}[/bold cyan]?")
        if not is_authorized:
            reason = Prompt.ask("Please provide a reason for the denial")
            return "User denied authorization: " + reason
        return None
    return None
