"""
Local AMI protocol test — simulates Asterisk 21 AMI response format.
Run with:  python test_ami_local.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from asterisk_ami import AsteriskAMI


# Asterisk 21 sends --END COMMAND-- as a bare line (no "Output: " prefix).
# The Response block may have some Output: lines (empty separators), but
# --END COMMAND-- arrives in a separate block WITHOUT an ActionID.

def pjsip_response(action_id: str) -> bytes:
    # Asterisk 21 format: all output in ONE Response block, no --END COMMAND--
    return (
        f"Response: Success\r\n"
        f"ActionID: {action_id}\r\n"
        f"Message: Command output follows\r\n"
        f"Output: \r\n"
        f"Output:  Endpoint:  6692/6692                                            Not in use    0 of inf\r\n"
        f"Output: \r\n"
        f"Output:  Endpoint:  6693/6693                                            Not in use    0 of inf\r\n"
        f"Output: \r\n"
        f"Output: Objects found: 2\r\n"
        f"Output: \r\n"
        f"\r\n"
    ).encode()


def uptime_response(action_id: str) -> bytes:
    # Asterisk 21 format: all output in ONE Response block, no --END COMMAND--
    return (
        f"Response: Success\r\n"
        f"ActionID: {action_id}\r\n"
        f"Message: Command output follows\r\n"
        f"Output: System uptime: 1 day\r\n"
        f"Output: Last reload: 1 day\r\n"
        f"\r\n"
    ).encode()


def parse_actions(data: bytes) -> list[dict]:
    """Split raw bytes into individual AMI action dicts."""
    actions = []
    for block in data.decode(errors="replace").split("\r\n\r\n"):
        block = block.strip()
        if not block:
            continue
        action = {}
        for line in block.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                action[k.strip()] = v.strip()
        if action:
            actions.append(action)
    return actions


async def mock_asterisk_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    writer.write(b"Asterisk Call Manager/9.0.0\r\n")
    await writer.drain()

    buf = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=3.0)
        except asyncio.TimeoutError:
            break
        if not chunk:
            break
        buf += chunk

        # Process all complete actions (terminated by \r\n\r\n)
        while b"\r\n\r\n" in buf:
            block_bytes, buf = buf.split(b"\r\n\r\n", 1)
            actions = parse_actions(block_bytes + b"\r\n\r\n")
            for action in actions:
                cmd = action.get("Action", "")
                action_id = action.get("ActionID", "")
                command = action.get("Command", "")

                if cmd == "Login":
                    writer.write(b"Response: Success\r\nMessage: Authentication accepted\r\n\r\n")
                elif cmd == "Command":
                    if "pjsip show endpoints" in command:
                        writer.write(pjsip_response(action_id))
                    elif "core show uptime" in command or "uptime" in command:
                        writer.write(uptime_response(action_id))
                    else:
                        writer.write(
                            f"Response: Success\r\nActionID: {action_id}\r\n"
                            f"Message: Command output follows\r\n"
                            f"--END COMMAND--\r\n\r\n".encode()
                        )
                await writer.drain()

    writer.close()


async def run_test():
    server = await asyncio.start_server(mock_asterisk_server, "127.0.0.1", 15038)

    import config
    config.settings.ami_host = "127.0.0.1"
    config.settings.ami_port = 15038
    config.settings.ami_username = "test"
    config.settings.ami_secret = "test"

    ami = AsteriskAMI()
    await ami.connect()
    print(f"Connected: {ami.is_connected}\n")

    tests = [
        ("sequential pjsip",    ami.send_command("pjsip show endpoints")),
    ]

    # Run sequential test first
    for name, coro in tests:
        try:
            result = await coro
            last = repr(result[-1]) if result else "n/a"
            print(f"PASS  {name}: {len(result)} lines, last={last}")
        except Exception as e:
            print(f"FAIL  {name}: {e}")

    # Run concurrent test (like real app does — extensions + monitoring at same time)
    print("\n--- Concurrent test ---")
    results = await asyncio.gather(
        ami.send_command("pjsip show endpoints"),
        ami.send_command("core show uptime"),
        return_exceptions=True,
    )
    names = ["pjsip show endpoints", "core show uptime"]
    all_ok = True
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"FAIL  {name}: {result}")
            all_ok = False
        else:
            last = repr(result[-1]) if result else "n/a"
            print(f"PASS  {name}: {len(result)} lines, last={last}")

    await ami.close()
    server.close()
    await server.wait_closed()

    print("\nAll tests PASSED" if all_ok else "\nSome tests FAILED")
    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)
