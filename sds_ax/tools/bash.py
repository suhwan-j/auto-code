from langchain_core.tools import tool
import asyncio


@tool
async def bash_tool(command: str, timeout: int = 120) -> str:
    """Execute a shell command.

    Args:
        command: Shell command to execute
        timeout: Timeout in seconds (default 120)
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return f"Command timed out after {timeout}s"

    output = stdout.decode() + stderr.decode()
    # Truncate very large outputs
    if len(output) > 50000:
        output = output[:50000] + f"\n... (truncated, {len(stdout.decode()) + len(stderr.decode())} total chars)"
    return output.strip() or "(no output)"
