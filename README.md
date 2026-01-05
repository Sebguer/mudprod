# mudprod

Integration testing framework for MUD (Multi-User Dungeon) servers.

mudprod connects to MUD servers via telnet, sends commands as a player would, and validates server responses. Think Selenium, but for text-based games.

## Installation

```bash
pip install mudprod

# With pytest integration
pip install mudprod[pytest]

# With HTML report generation
pip install mudprod[pytest,html]
```

## Quick Start

```python
from mudprod import MUDClient, assert_contains

# Connect to server
client = MUDClient("localhost", 4000)
client.connect()

# Login (raw commands)
client.send_raw("myusername\n")
client.send_raw("mypassword\n")

# Send commands and validate responses
response = client.send_command("look")
assert_contains(response, "Exits:")

response = client.send_command("who")
assert response.prompt_detected

client.disconnect()
```

## Login Configuration

Different MUDs have different login flows. Use `LoginConfig` to handle yours:

```python
from mudprod import MUDClient, LoginConfig

client = MUDClient("localhost", 4000)
client.connect()

# Configure login flow
login = LoginConfig(
    steps=[
        ("name:", "myusername"),      # Wait for "name:", send username
        ("password:", "mypassword"),  # Wait for "password:", send password
        ("selection:", "1"),          # Wait for menu, select option 1
    ],
    success_patterns=[r"Welcome back", r">\s*$"],
    failure_patterns=[r"Invalid", r"incorrect"],
)

if client.login(login):
    response = client.send_command("look")
    print(response.clean)

client.disconnect()
```

## Prompt Detection

mudprod needs to know when the server is done sending output. Configure prompt detection for your MUD:

```python
from mudprod import MUDClient, PromptConfig

# Default: looks for >, :, or ] at end of output
client = MUDClient("localhost", 4000)

# Custom patterns
prompt_config = PromptConfig(
    patterns=[
        r"HP:\d+ SP:\d+ >",     # Health/spell point prompt
        r"\[\d+h \d+m\]>",      # Bracketed prompt
        r"Command:\s*$",        # Custom command prompt
    ],
    end_chars=">]:",
)
client = MUDClient("localhost", 4000, prompt_config=prompt_config)

# Fully custom detection
def my_detector(text: str) -> bool:
    return text.rstrip().endswith(">>>")

prompt_config = PromptConfig(custom_detector=my_detector)
client = MUDClient("localhost", 4000, prompt_config=prompt_config)
```

## Assertions

mudprod provides assertion helpers with clear error messages:

```python
from mudprod import (
    assert_contains,
    assert_not_contains,
    assert_matches,
    assert_prompt,
    assert_line_count,
)

response = client.send_command("look")

# Check for text (case-insensitive)
assert_contains(response, "exits:", case_sensitive=False)

# Check text is NOT present
assert_not_contains(response, "error", case_sensitive=False)

# Regex matching with capture groups
match = assert_matches(response, r"HP: (\d+)/(\d+)")
current_hp = int(match.group(1))

# Verify prompt was received
assert_prompt(response)

# Check line count
assert_line_count(response, min_lines=3, max_lines=50)
```

## pytest Integration

mudprod works great with pytest:

```python
# conftest.py
import pytest
from mudprod import MUDClient, LoginConfig

@pytest.fixture
def client():
    c = MUDClient("localhost", 4000)
    assert c.connect(), "Could not connect to server"

    login = LoginConfig(steps=[
        ("name:", "testuser"),
        ("password:", "testpass"),
    ])
    assert c.login(login), "Could not login"

    yield c
    c.disconnect()


# test_commands.py
from mudprod import assert_contains

def test_look_command(client):
    response = client.send_command("look")
    assert response.prompt_detected
    assert_contains(response, "Exits:")

def test_who_command(client):
    response = client.send_command("who")
    assert_contains(response, "players online", case_sensitive=False)
```

Run with:

```bash
pytest tests/ -v
pytest tests/ -v --html=report.html  # With HTML report
```

## API Reference

### MUDClient

| Method | Description |
|--------|-------------|
| `connect()` | Establish TCP connection, returns bool |
| `disconnect()` | Close connection |
| `login(config)` | Execute login flow, returns bool |
| `send_command(cmd)` | Send command, wait for response, returns MUDResponse |
| `send_raw(data)` | Send raw data without waiting |
| `read_available()` | Read any pending data, returns MUDResponse |
| `wait_for_pattern(pattern, timeout)` | Wait for specific output |

### MUDResponse

| Property | Type | Description |
|----------|------|-------------|
| `raw` | str | Raw server output with ANSI codes |
| `clean` | str | Cleaned output (ANSI stripped) |
| `lines` | List[str] | Non-empty lines |
| `prompt_detected` | bool | Whether prompt was seen |

### Assertions

| Function | Description |
|----------|-------------|
| `assert_contains(response, pattern)` | Check text is present |
| `assert_not_contains(response, pattern)` | Check text is NOT present |
| `assert_matches(response, regex)` | Regex match, returns Match object |
| `assert_prompt(response)` | Check prompt was detected |
| `assert_line_count(response, min, max)` | Check line count |

## License

MIT License - see LICENSE file for details.
