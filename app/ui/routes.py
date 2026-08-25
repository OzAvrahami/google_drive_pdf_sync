"""Single route-definition source for the Panda 2.0 shell."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.ui.models.queue_policy import QueueRoute
from app.ui.theme.icons import IconName


class AppRoute(str, Enum):
    OVERVIEW = "overview"
    INBOX = QueueRoute.INBOX.value
    ATTENTION = QueueRoute.ATTENTION.value
    READY = QueueRoute.READY.value
    IRRELEVANT = QueueRoute.IRRELEVANT.value
    HISTORY = QueueRoute.HISTORY.value


class RouteViewKind(str, Enum):
    OVERVIEW = "overview"
    DOCUMENT_QUEUE = "document_queue"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    route: AppRoute
    label_he: str
    icon: IconName
    show_count: bool
    view_kind: RouteViewKind
    accessible_description: str
    queue_route: QueueRoute | None = None


ROUTES: tuple[RouteDefinition, ...] = (
    RouteDefinition(
        AppRoute.OVERVIEW,
        "סקירה",
        IconName.OVERVIEW,
        False,
        RouteViewKind.OVERVIEW,
        "סקירת העבודה הנוכחית",
    ),
    RouteDefinition(
        AppRoute.INBOX,
        "נכנסו",
        IconName.INBOX,
        True,
        RouteViewKind.DOCUMENT_QUEUE,
        "מסמכים חדשים הממתינים לעיבוד",
        QueueRoute.INBOX,
    ),
    RouteDefinition(
        AppRoute.ATTENTION,
        "דורש טיפול",
        IconName.WARNING,
        True,
        RouteViewKind.DOCUMENT_QUEUE,
        "מסמכים שדורשים בדיקה או טיפול",
        QueueRoute.ATTENTION,
    ),
    RouteDefinition(
        AppRoute.READY,
        "מוכן",
        IconName.SUCCESS,
        True,
        RouteViewKind.READY,
        "מסמכים שמוכנים לאישור או לייצוא",
        QueueRoute.READY,
    ),
    RouteDefinition(
        AppRoute.IRRELEVANT,
        "לא רלוונטי",
        IconName.TRASH,
        True,
        RouteViewKind.DOCUMENT_QUEUE,
        "מסמכים שסומנו כלא רלוונטיים",
        QueueRoute.IRRELEVANT,
    ),
    RouteDefinition(
        AppRoute.HISTORY,
        "היסטוריה",
        IconName.ARCHIVE,
        True,
        RouteViewKind.DOCUMENT_QUEUE,
        "מסמכים שיוצאו בעבר",
        QueueRoute.HISTORY,
    ),
)

ROUTE_BY_ID = {definition.route: definition for definition in ROUTES}


def route_definition(route: AppRoute | str) -> RouteDefinition:
    try:
        return ROUTE_BY_ID[AppRoute(route)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unknown Panda 2.0 route: {route!r}") from exc
