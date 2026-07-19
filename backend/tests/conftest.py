"""
Shared pytest configuration.

pytest_addoption MUST live in conftest.py — pytest does not pick up custom
CLI options declared inside a regular test module.
"""


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live LLM evaluation against the labeled test set (costs API credits).",
    )
