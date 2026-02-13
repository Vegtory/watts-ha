# Contributing to Watts SmartHome Integration

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Home Assistant development environment
- Git

### Clone and Setup

```bash
git clone https://github.com/Vegtory/watts-ha.git
cd watts-ha
pip install -r requirements-test.txt
```

### Development Installation

For testing in a live Home Assistant instance:

```bash
# Link to your HA config directory
ln -s $(pwd)/custom_components/watts_smarthome ~/.homeassistant/custom_components/watts_smarthome

# Restart Home Assistant
```

## Code Structure

```
watts-ha/
├── custom_components/watts_smarthome/
│   ├── __init__.py          # Integration setup/teardown
│   ├── api.py               # API client
│   ├── config_flow.py       # UI configuration
│   ├── const.py             # Constants
│   ├── coordinator.py       # Data coordinator
│   ├── diagnostics.py       # Diagnostics support
│   ├── manifest.json        # Integration metadata
│   ├── number.py            # Number entities
│   ├── select.py            # Select entities
│   ├── sensor.py            # Sensor entities
│   ├── services.yaml        # Service definitions
│   ├── strings.json         # UI strings
│   └── translations/
│       └── en.json          # English translations
├── tests/                   # Unit tests
├── README.md                # User documentation
├── ARCHITECTURE.md          # Technical architecture
└── INSTALL.md              # Installation guide
```

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/)
- Use type hints for all functions
- Maximum line length: 100 characters
- Use `black` for formatting (if available)
- Use `ruff` or `flake8` for linting

### Home Assistant Guidelines

- Follow [HA development guidelines](https://developers.home-assistant.io/docs/development_index)
- Use `async`/`await` for all I/O operations
- Avoid blocking the event loop
- Use `_LOGGER.debug()` for verbose logging
- Never log secrets or tokens

### Code Quality

```python
# Good: Type hints and docstrings
async def async_get_user_data(self, lang: str = "en") -> dict[str, Any]:
    """Get user profile and smarthomes.
    
    Args:
        lang: Language code for API responses.
        
    Returns:
        User data dictionary from API.
    """
    data = {"lang": lang}
    return await self._request("POST", ENDPOINT_USER_READ, data=data)

# Bad: No types, no docs
async def get_user(self, lang="en"):
    return await self._request("POST", ENDPOINT_USER_READ, {"lang": lang})
```

## Testing

### Run Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_api.py

# With coverage
pytest --cov=custom_components.watts_smarthome
```

### Writing Tests

```python
@pytest.mark.asyncio
async def test_feature(api_client, mock_session):
    """Test description."""
    # Arrange
    mock_response = AsyncMock()
    mock_response.status = 200
    
    # Act
    result = await api_client.some_method()
    
    # Assert
    assert result["expected_key"] == "expected_value"
```

### Manual Testing

1. Install in test HA instance
2. Set up with test credentials
3. Verify all entities appear
4. Test all services
5. Check diagnostics
6. Test with multiple accounts

## Making Changes

### Workflow

1. **Fork and Branch**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make Changes**
   - Write code
   - Add tests
   - Update documentation

3. **Test**
   ```bash
   pytest tests/
   python3 -m py_compile custom_components/watts_smarthome/*.py
   ```

4. **Commit**
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

5. **Push and PR**
   ```bash
   git push origin feature/your-feature
   # Open PR on GitHub
   ```

### Commit Messages

Use conventional commits:

- `feat: add climate entity support`
- `fix: handle null temperature values`
- `docs: update README with new features`
- `test: add tests for coordinator`
- `refactor: simplify API client error handling`

## Adding Features

### New Entity Type

1. Create platform file (e.g., `climate.py`)
2. Add to `PLATFORMS` in `const.py`
3. Implement entity class extending `CoordinatorEntity`
4. Add tests
5. Update README

### New Service

1. Define schema in `__init__.py`
2. Implement handler in `async_setup_entry`
3. Add to `services.yaml`
4. Add tests
5. Document in README

### New API Endpoint

1. Add constant in `const.py`
2. Add method in `api.py`
3. Update coordinator if needed for data fetching
4. Add tests with mocked responses

## Debugging

### Enable Detailed Logging

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.watts_smarthome: debug
```

### Debug in VS Code

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Home Assistant",
            "type": "python",
            "request": "attach",
            "port": 5678,
            "host": "localhost"
        }
    ]
}
```

### Common Issues

**Import Errors**: Ensure HA dependencies installed
```bash
pip install homeassistant voluptuous aiohttp
```

**Async Issues**: Always use `await` for async calls

**Token Issues**: Check token refresh logic in `api.py`

## Documentation

### Updating README

- Keep user-focused
- Include examples
- Update entity list if changed
- Add screenshots if UI changes

### Updating ARCHITECTURE

- Explain design decisions
- Document data flows
- Keep technical details current

### Translation Support

To add a new language:

1. Copy `translations/en.json` to `translations/{lang}.json`
2. Translate all strings
3. Test in HA with that language

## Release Process

1. Update version in `manifest.json`
2. Update CHANGELOG.md (if exists)
3. Tag release: `git tag v0.1.1`
4. Push tags: `git push --tags`
5. GitHub Actions will create release (if configured)

## Code Review Checklist

Before submitting PR:

- [ ] Code follows HA guidelines
- [ ] All tests pass
- [ ] New features have tests
- [ ] Documentation updated
- [ ] No secrets in code
- [ ] Type hints present
- [ ] Logging appropriate (no token logging)
- [ ] Error handling robust
- [ ] Backwards compatible (if applicable)

## Getting Help

- **HA Discord**: #devs channel
- **HA Forums**: Development section
- **Issues**: GitHub issues for bugs
- **Discussions**: GitHub discussions for questions

## License

By contributing, you agree your contributions will be licensed under the same license as the project.
