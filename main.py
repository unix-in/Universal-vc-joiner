import asyncio
import os
import shlex
import sys
from typing import List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from core.config import ConfigManager
from core.manager import VoiceJoinerManager

console = Console()

BANNER = """
[bold cyan]╭・VOICE JOINER[/bold cyan]
[bold magenta]╰・Fully Customizable Voice Presence[/bold magenta]
[dim]Multi-Account Voice Channel Automation & Rich Presence Engine[/dim]
[cyan]Developed by:[/cyan] [bold white]Saint[/bold white] [dim]|[/dim] [magenta]Discord:[/magenta] [bold yellow]xqfb[/bold yellow]
"""

HELP_TEXT = """
[bold yellow]Available Commands:[/bold yellow]
  [cyan]/vc join <channel_id> [account][/cyan]
      Join voice channel (e.g., [green]/vc join 123456789 all[/green] or [green]/vc join 123456789 1[/green])
  
  [cyan]/vc leave [account][/cyan]
      Leave voice channel (e.g., [green]/vc leave 1[/green] or [green]/vc leave all[/green])

  [cyan]/vc stream <account> <game/title> [twitch_url][/cyan]
      Set streaming presence in VC (e.g., [green]/vc stream 1 Valorant https://twitch.tv/shroud[/green])

  [cyan]/vc music <account> <song_name> [artist][/cyan]
      Set Spotify music presence (e.g., [green]/vc music 2 Starboy "The Weeknd"[/green])

  [cyan]/vc activity <account> <type> <name> [details] [state][/cyan]
      Set custom activity (types: [white]playing, streaming, listening, watching, custom, none[/white])
      Example: [green]/vc activity 3 playing Minecraft "Survival" "Building Base"[/green]

  [cyan]/vc status <account> <online|idle|dnd|invisible>[/cyan]
      Change status mode (e.g., [green]/vc status 4 idle[/green])

  [cyan]/vc custom <account> <text> [emoji][/cyan]
      Set custom status message (e.g., [green]/vc custom 4 "In a private VC" 🎧[/green])

  [cyan]/vc mute <account> [on|off][/cyan]
      Toggle or set self-mute in VC

  [cyan]/vc deaf <account> [on|off][/cyan]
      Toggle or set self-deafen in VC

  [cyan]/vc video <account> [on|off][/cyan]
      Toggle or set camera/screenshare icon in VC

  [cyan]/vc list[/cyan]
      Display current status of all accounts

  [cyan]/vc add <token> [name][/cyan]
      Add a new account dynamically

  [cyan]/vc remove <account>[/cyan]
      Remove an account by name or index

  [cyan]/vc import[/cyan]
      Import new tokens from [white]tokens.txt[/white]

  [cyan]/vc save[/cyan]
      Save all current settings to [white]config.json[/white]

  [cyan]/vc exit / quit[/cyan]
      Leave all VCs and close program

[dim]* Commands can also be typed without '/vc ' prefix[/dim]
"""

def print_banner():
    console.print(Panel(BANNER, border_style="cyan"))

def display_accounts_table(manager: VoiceJoinerManager):
    table = Table(title="Authorized Voice Presences", border_style="blue", header_style="bold magenta")
    table.add_column("No", style="dim", width=4)
    table.add_column("Account", style="bold white", width=14)
    table.add_column("Discord User", style="cyan", width=20)
    table.add_column("Connection", style="bold", width=14)
    table.add_column("Voice Channel", style="yellow", width=20)
    table.add_column("Mic/Deaf/Cam", width=12)
    table.add_column("Status", width=10)
    table.add_column("Current Presence / Activity", style="green")

    clients = manager.get_all_clients()
    if not clients:
        table.add_row("-", "No Accounts", "None Loaded", "IDLE", "-", "-", "-", "Add tokens to config.json or tokens.txt")
        console.print(table)
        return

    for idx, client in enumerate(clients, 1):
        if client.in_vc:
            conn_text = "[bold green]IN VC[/bold green]"
        elif client.state_desc == "READY":
            conn_text = "[green]ONLINE[/green]"
        elif client.state_desc == "CONNECTING":
            conn_text = "[yellow]CONNECTING[/yellow]"
        elif client.state_desc == "INVALID_TOKEN":
            conn_text = "[bold red]INVALID TOKEN[/bold red]"
        else:
            conn_text = f"[dim]{client.state_desc}[/dim]"

        mic = "🔇" if client.self_mute else "🎤"
        deaf = "🔕" if client.self_deaf else "🎧"
        cam = "📹" if client.self_video else "·"
        audio_icons = f"{mic} {deaf} {cam}"

        status_lower = client.status.lower()
        if status_lower == "online":
            st_badge = "[green]● Online[/green]"
        elif status_lower == "idle":
            st_badge = "[yellow]🌙 Idle[/yellow]"
        elif status_lower == "dnd":
            st_badge = "[red]⛔ DND[/red]"
        else:
            st_badge = "[dim]○ Invisible[/dim]"

        activity = client.activity or {}
        act_type = activity.get("type", "none").lower()
        act_name = activity.get("name", "")

        if act_type == "streaming":
            act_str = f"[magenta]🟣 Streaming {act_name}[/magenta]"
        elif act_type == "listening":
            details = activity.get("details", "")
            state = activity.get("state", "")
            act_str = f"[green]🟢 Listening to {act_name}[/green]"
            if details:
                separator = f" - {state}" if state else ""
                act_str += f" ({details}{separator})"
        elif act_type == "playing":
            act_str = f"[cyan]🎮 Playing {act_name}[/cyan]"
        elif act_type == "watching":
            act_str = f"[yellow]📺 Watching {act_name}[/yellow]"
        elif act_type == "custom":
            emoji = activity.get("emoji", "")
            state = activity.get("state", act_name)
            act_str = f"[white]{emoji} {state}[/white]".strip()
        else:
            act_str = "[dim]None (VC Only)[/dim]"

        vc_display = client.current_channel_name or client.channel_id or "[dim]Not in VC[/dim]"

        table.add_row(
            str(idx),
            client.name,
            client.username,
            conn_text,
            str(vc_display),
            audio_icons,
            st_badge,
            act_str
        )

    console.print(table)

async def handle_command(cmd_line: str, manager: VoiceJoinerManager) -> bool:
    cmd_line = cmd_line.strip()
    if not cmd_line:
        return True

    if cmd_line.startswith("/vc "):
        cmd_line = cmd_line[4:].strip()
    elif cmd_line.startswith("/"):
        cmd_line = cmd_line[1:].strip()

    try:
        parts = shlex.split(cmd_line)
    except Exception as e:
        console.print(f"[red]Error parsing command: {e}[/red]")
        return True

    if not parts:
        return True

    action = parts[0].lower()
    args = parts[1:]

    if action in ("exit", "quit", "q"):
        console.print("[yellow]Disconnecting all accounts and exiting...[/yellow]")
        await manager.stop()
        return False

    if action in ("help", "?"):
        console.print(HELP_TEXT)

    elif action in ("list", "status_all", "ls"):
        display_accounts_table(manager)

    elif action == "join":
        if not args:
            console.print("[red]Usage: /vc join <channel_id> [account_name/index/all][/red]")
            return True
        channel_id = args[0]
        selector = args[1] if len(args) > 1 else "all"
        joined = await manager.join_vc(selector, channel_id)
        if joined:
            console.print(f"[green]✓ Joined VC {channel_id} on: {', '.join(joined)}[/green]")
        else:
            console.print(f"[red]✗ Failed to join VC for selector '{selector}'[/red]")

    elif action == "leave":
        selector = args[0] if args else "all"
        left = await manager.leave_vc(selector)
        if left:
            console.print(f"[yellow]✓ Left VC for: {', '.join(left)}[/yellow]")
        else:
            console.print(f"[red]✗ No accounts left VC for selector '{selector}'[/red]")

    elif action == "stream":
        if len(args) < 2:
            console.print("[red]Usage: /vc stream <account> <title> [twitch_url][/red]")
            return True
        selector = args[0]
        title = args[1]
        url = args[2] if len(args) > 2 else "https://www.twitch.tv/discord"
        updated = await manager.set_stream(selector, title=title, url=url)
        if updated:
            console.print(f"[magenta]✓ Set Streaming presence '{title}' for: {', '.join(updated)}[/magenta]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "music":
        if len(args) < 2:
            console.print("[red]Usage: /vc music <account> <song_name> [artist][/red]")
            return True
        selector = args[0]
        song = args[1]
        artist = args[2] if len(args) > 2 else ""
        updated = await manager.set_music(selector, song=song, artist=artist)
        if updated:
            console.print(f"[green]✓ Set Music presence '{song}' by '{artist}' for: {', '.join(updated)}[/green]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "status":
        if len(args) < 2:
            console.print("[red]Usage: /vc status <account> <online|idle|dnd|invisible>[/red]")
            return True
        selector = args[0]
        st = args[1].lower()
        if st not in ("online", "idle", "dnd", "invisible"):
            console.print("[red]Invalid status. Options: online, idle, dnd, invisible[/red]")
            return True
        updated = await manager.set_status(selector, st)
        if updated:
            console.print(f"[green]✓ Set status to '{st}' for: {', '.join(updated)}[/green]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "custom":
        if len(args) < 2:
            console.print("[red]Usage: /vc custom <account> <text> [emoji][/red]")
            return True
        selector = args[0]
        text = args[1]
        emoji = args[2] if len(args) > 2 else None
        updated = await manager.set_activity(selector, activity_type="custom", name="Custom Status", state=text, emoji=emoji)
        if updated:
            console.print(f"[green]✓ Set custom status '{text}' for: {', '.join(updated)}[/green]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "activity":
        if len(args) < 3:
            console.print("[red]Usage: /vc activity <account> <type> <name> [details] [state][/red]")
            console.print("[dim]Types: playing, streaming, listening, watching, custom, none[/dim]")
            return True
        selector = args[0]
        act_type = args[1].lower()
        name = args[2]
        details = args[3] if len(args) > 3 else None
        state = args[4] if len(args) > 4 else None
        updated = await manager.set_activity(selector, activity_type=act_type, name=name, details=details, state=state)
        if updated:
            console.print(f"[green]✓ Set activity ({act_type}: {name}) for: {', '.join(updated)}[/green]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "mute":
        if not args:
            console.print("[red]Usage: /vc mute <account> [on|off][/red]")
            return True
        selector = args[0]
        is_on = True if len(args) == 1 or args[1].lower() in ("on", "true", "1") else False
        updated = await manager.set_voice_state(selector, mute=is_on)
        if updated:
            console.print(f"[yellow]✓ Set mute={is_on} for: {', '.join(updated)}[/yellow]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "deaf":
        if not args:
            console.print("[red]Usage: /vc deaf <account> [on|off][/red]")
            return True
        selector = args[0]
        is_on = True if len(args) == 1 or args[1].lower() in ("on", "true", "1") else False
        updated = await manager.set_voice_state(selector, deaf=is_on)
        if updated:
            console.print(f"[yellow]✓ Set deafen={is_on} for: {', '.join(updated)}[/yellow]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "video":
        if not args:
            console.print("[red]Usage: /vc video <account> [on|off][/red]")
            return True
        selector = args[0]
        is_on = True if len(args) == 1 or args[1].lower() in ("on", "true", "1") else False
        updated = await manager.set_voice_state(selector, video=is_on)
        if updated:
            console.print(f"[yellow]✓ Set video={is_on} for: {', '.join(updated)}[/yellow]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "add":
        if not args:
            console.print("[red]Usage: /vc add <token> [name][/red]")
            return True
        token = args[0]
        name = args[1] if len(args) > 1 else None
        client = await manager.add_account(token=token, name=name)
        if client:
            console.print(f"[green]✓ Added and connecting account '{client.name}'[/green]")
        else:
            console.print("[red]✗ Failed to add account.[/red]")

    elif action == "remove":
        if not args:
            console.print("[red]Usage: /vc remove <account_name/index>[/red]")
            return True
        selector = args[0]
        ok = await manager.remove_account(selector)
        if ok:
            console.print(f"[yellow]✓ Removed account '{selector}'[/yellow]")
        else:
            console.print(f"[red]✗ Account '{selector}' not found.[/red]")

    elif action == "import":
        imported = manager.config_manager.import_tokens_from_file()
        console.print(f"[green]✓ Imported {imported} new account(s) from tokens.txt[/green]")
        if imported > 0:
            manager.init_clients_from_config()
            await manager.start()

    elif action == "save":
        ok = manager.config_manager.save()
        if ok:
            console.print("[green]✓ Configurations saved to config.json[/green]")
        else:
            console.print("[red]✗ Failed to save configuration file.[/red]")

    else:
        console.print(f"[red]Unknown command: '{action}'. Type '/vc help' for available commands.[/red]")

    return True

async def cli_loop(manager: VoiceJoinerManager):
    print_banner()
    console.print("[cyan]Initializing accounts from config.json...[/cyan]")
    await manager.start()
    await asyncio.sleep(1.5)

    display_accounts_table(manager)
    console.print("\n[bold green]Status: READY FOR CONFIGURATION[/bold green]")
    console.print("[dim]Type '/vc help' for list of commands, or '/vc exit' to quit.[/dim]\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            cmd = await loop.run_in_executor(None, input, "vc-joiner > ")
            cont = await handle_command(cmd, manager)
            if not cont:
                break
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Shutting down...[/yellow]")
            await manager.stop()
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")

def main():
    config_mgr = ConfigManager()
    manager = VoiceJoinerManager(config_mgr)
    try:
        asyncio.run(cli_loop(manager))
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
