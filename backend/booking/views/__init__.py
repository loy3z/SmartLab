"""HTTP layer split by area.

Import views from ``booking.views`` as before; each module re-exports its public view classes.
"""

from .auth import *  # noqa: F401,F403
from .resources import *  # noqa: F401,F403
from .bookings import *  # noqa: F401,F403
from .admin import *  # noqa: F401,F403
from .outlook import *  # noqa: F401,F403
from .notifications import *  # noqa: F401,F403
from .calendar import *  # noqa: F401,F403
from .series import *  # noqa: F401,F403
from .misc import *  # noqa: F401,F403
from .announcements import *  # noqa: F401,F403
