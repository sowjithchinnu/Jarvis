"""
Risk tiering for agent actions.

The idea: not every action deserves a confirmation prompt. Read-only /
information-gathering actions run automatically. Anything that changes
state on a page (clicking, typing, submitting) needs a human nod first,
with submit/high-stakes actions getting the most explicit confirmation.

Extend this table as you add more tools.
"""

LOW = "low"
MEDIUM = "medium"
HIGH = "high"

RISK_TIERS = {
    "search_web": LOW,
    "open_url": LOW,
    "read_page_text": LOW,
    "list_interactive_elements": LOW,
    "click_element": MEDIUM,
    "fill_field": MEDIUM,
    "submit_form": HIGH,
    "go_back": LOW,
    "undo_last_action": MEDIUM,
    "take_screenshot": LOW,
    "get_volume": LOW,
    "get_clipboard": LOW,
    "get_battery_status": LOW,
    "get_system_status": LOW,
    "get_brightness": LOW,
    "get_last_download_info": LOW,
    # Volume changes are reversible and have no data-loss potential; raise to
    # MEDIUM if future behavior introduces broader system-side effects.
    "set_volume": LOW,
    "set_clipboard": LOW,
    "set_brightness": LOW,
    # Application launches are MEDIUM because they spawn a real running
    # process rather than merely toggling a reversible system value.
    "open_application": MEDIUM,
    "send_notification": LOW,
    "list_directory": LOW,
    "read_text_file": LOW,
    "remember_fact": LOW,
    "list_facts": LOW,
    "forget_fact": LOW,
}

TOOL_ARG_SCHEMAS = {
    "take_screenshot": {"required": set(), "allowed": set()},
    "get_volume": {"required": set(), "allowed": set()},
    "set_volume": {"required": {"level"}, "allowed": {"level"}},
    "get_clipboard": {"required": set(), "allowed": set()},
    "set_clipboard": {"required": {"text"}, "allowed": {"text"}},
    "get_battery_status": {"required": set(), "allowed": set()},
    "get_system_status": {"required": set(), "allowed": set()},
    "get_brightness": {"required": set(), "allowed": set()},
    "set_brightness": {"required": {"level"}, "allowed": {"level"}},
    "open_application": {"required": {"app_name"}, "allowed": {"app_name"}},
    "send_notification": {
        "required": {"title", "message"},
        "allowed": {"title", "message"},
    },
    "list_directory": {"required": {"path"}, "allowed": {"path"}},
    "read_text_file": {"required": {"path"}, "allowed": {"path"}},
    "get_last_download_info": {"required": set(), "allowed": set()},
    "remember_fact": {"required": {"text"}, "allowed": {"text"}},
    "list_facts": {"required": set(), "allowed": set()},
    "forget_fact": {"required": {"match_text"}, "allowed": {"match_text"}},
}


def get_risk(tool_name: str) -> str:
    return RISK_TIERS.get(tool_name, HIGH)  # unknown tools default to HIGH (safe default)


def describe_action(tool_name: str, args: dict) -> str:
    """
    Human-readable summary of what the agent is about to do, shown in the
    confirmation dialog. Keep it plain-language, not a dump of raw args.
    """
    if tool_name == "click_element":
        # This risk layer does not have the browser DOM, so it cannot reliably
        # inspect link text or hrefs for download hints. The existing
        # click_element confirmation still applies, and any download is
        # reported post-click by BrowserExecutor's result message.
        return (
            f"Click on element '{args.get('element_id')}'. "
            "It may download a file to your computer."
        )
    if tool_name == "fill_field":
        return f"Type '{args.get('value')}' into field '{args.get('element_id')}'."
    if tool_name == "submit_form":
        return f"Submit the form (element '{args.get('element_id')}'). This may send data or trigger a purchase/login/etc."
    if tool_name == "open_url":
        return f"Open URL: {args.get('url')}"
    if tool_name == "undo_last_action":
        return "Undo the most recent reversible browser action."
    if tool_name == "take_screenshot":
        return "Capture a screenshot of the local desktop. It may contain sensitive information."
    if tool_name == "set_volume":
        return f"Set system volume to {args.get('level')}%."
    if tool_name == "set_brightness":
        return f"Set screen brightness to {args.get('level')}%."
    if tool_name == "set_clipboard":
        text = str(args.get("text", ""))
        preview = text if len(text) <= 100 else f"{text[:97]}..."
        return f"Set clipboard to: {preview}"
    if tool_name == "open_application":
        return f"Open application: {args.get('app_name')}."
    if tool_name == "remember_fact":
        return "Remember this preference or task context for future sessions."
    if tool_name == "forget_fact":
        return f"Forget remembered facts matching '{args.get('match_text')}'."
    if tool_name == "search_web":
        return f"Search the web for: {args.get('query')}"
    return f"Run action '{tool_name}' with arguments: {args}"
