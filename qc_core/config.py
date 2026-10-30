from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
AUTH_DIR = BASE_DIR / ".auth"
AUTH_STATE_FILE = AUTH_DIR / "storage_state.json"

# Canvas Defaults
DEFAULT_COURSE_ID = "350"
DEFAULT_CANVAS_DOMAIN = "https://www.ole.mumbai.bristol.ac.uk"
DEFAULT_COURSE_URL = f"{DEFAULT_CANVAS_DOMAIN}/courses/{DEFAULT_COURSE_ID}"
DEFAULT_MODULES_URL = f"{DEFAULT_COURSE_URL}/modules"

# Timeouts (in milliseconds or seconds where noted)
PAGE_NAV_TIMEOUT_MS = 35000
LINK_CHECK_TIMEOUT_MS = 12000
CONTENT_STABILIZE_WAIT_MS = 2000

# Patterns that indicate an authentication wall or SSO redirect rather than a broken link
SSO_LOGIN_PATTERNS = [
    "/login",
    "sso",
    "idp",
    "shibboleth",
    "adfs",
    "cas",
    "auth",
    "microsoftonline",
    "duosecurity",
    "okta",
    "accounts.google",
    "canvas-identity",
]

# Ensure working output directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUTH_DIR.mkdir(parents=True, exist_ok=True)
