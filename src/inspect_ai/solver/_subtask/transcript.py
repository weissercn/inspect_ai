import contextlib
from contextvars import ContextVar
from datetime import datetime
from logging import getLogger
from typing import (
    Any,
    Callable,
    Iterator,
    Literal,
    TypeAlias,
    Union,
)

import mmh3
from pydantic import BaseModel, Field, JsonValue, field_serializer

from inspect_ai._util.constants import SAMPLE_SUBTASK
from inspect_ai._util.content import Content, ContentImage, ContentText
from inspect_ai._util.json import JsonChange, json_changes
from inspect_ai.log._message import LoggingMessage
from inspect_ai.model._chat_message import ChatMessage
from inspect_ai.model._generate_config import GenerateConfig
from inspect_ai.model._model_output import ModelOutput
from inspect_ai.scorer._metric import Score
from inspect_ai.tool._tool_choice import ToolChoice
from inspect_ai.tool._tool_info import ToolInfo

from .._task_state import state_jsonable
from .store import store, store_changes, store_jsonable

logger = getLogger(__name__)


class BaseEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    """Time at which event occurred."""

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.astimezone().isoformat()


class StoreEvent(BaseEvent):
    """Change to data within the current `Store`."""

    event: Literal["store"] = Field(default="store")
    """Event type."""

    changes: list[JsonChange]
    """List of changes to the `Store`."""


class StateEvent(BaseEvent):
    """Change to the current `TaskState`"""

    event: Literal["state"] = Field(default="state")
    """Event type."""

    changes: list[JsonChange]
    """List of changes to the `TaskState`"""


class ModelEvent(BaseEvent):
    """Call to a language model."""

    event: Literal["model"] = Field(default="model")
    """Event type."""

    model: str
    """Model name."""

    input: list[ChatMessage]
    """Model input (list of messages)."""

    tools: list[ToolInfo]
    """Tools available to the model."""

    tool_choice: ToolChoice
    """Directive to the model which tools to prefer."""

    config: GenerateConfig
    """Generate config used for call to model."""

    output: ModelOutput
    """Output from model."""


class LoggerEvent(BaseEvent):
    """Log message recorded with Python logger."""

    event: Literal["logger"] = Field(default="logger")
    """Event type."""

    message: LoggingMessage
    """Logging message"""


class InfoEvent(BaseEvent):
    """Event with custom info/data."""

    event: Literal["info"] = Field(default="info")
    """Event type."""

    data: JsonValue
    """Data provided with event."""


class ScoreEvent(BaseEvent):
    """Event with sample score."""

    event: Literal["score"] = Field(default="score")
    """Event type."""

    score: Score
    """Sample score."""


class StepEvent(BaseEvent):
    """Step within current sample or subtask."""

    event: Literal["step"] = Field(default="step")
    """Event type."""

    action: Literal["begin", "end"]
    """Designates beginning or end of event."""

    type: str | None = Field(default=None)
    """Optional 'type' field for events"""

    name: str
    """Event name."""


class EvalEvents(BaseModel):
    events: list["Event"] = Field(default_factory=list)
    """List of events."""

    content: dict[str, str] = Field(default_factory=dict)
    """Content references."""


class SubtaskEvent(BaseEvent):
    """Subtask spawned."""

    event: Literal["subtask"] = Field(default="subtask")
    """Event type."""

    name: str
    """Name of subtask function."""

    input: dict[str, Any]
    """Subtask function inputs."""

    result: Any
    """Subtask function result."""

    events: EvalEvents
    """Transcript of events for subtask."""


Event: TypeAlias = Union[
    StateEvent
    | StoreEvent
    | ModelEvent
    | ScoreEvent
    | LoggerEvent
    | InfoEvent
    | StepEvent
    | SubtaskEvent,
]
"""Event in a transcript."""


class Transcript:
    """Transcript of events."""

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.events: list[Event] = []

    def info(self, data: JsonValue) -> None:
        """Add an `InfoEvent` to the transcript.

        Args:
           data (JsonValue): Data associated with the event.
        """
        self._event(InfoEvent(data=data))

    @contextlib.contextmanager
    def step(self, name: str, type: str | None = None) -> Iterator[None]:
        """Context manager for recording StepEvent.

        Args:
            name (str): Step name.
            type (str | None): Optional step type.
        """
        # step event
        self._event(StepEvent(action="begin", name=name, type=type))

        # run the step (tracking state/store changes)
        with track_state_changes(type), track_store_changes():
            yield

        # end step event
        self._event(StepEvent(action="end", name=name, type=type))

    def _event(self, event: Event) -> None:
        self.events.append(event)


def transcript() -> Transcript:
    """Get the current `Transcript`."""
    return _transcript.get()


@contextlib.contextmanager
def track_store_changes() -> Iterator[None]:
    before = store_jsonable(store())
    yield
    after = store_jsonable(store())

    changes = store_changes(before, after)
    if changes:
        transcript()._event(StoreEvent(changes=changes))


@contextlib.contextmanager
def track_state_changes(type: str | None = None) -> Iterator[None]:
    # we only want to track for step() inside the the sample
    # (solver level tracking is handled already and there are
    # no state changes in subtasks)
    if transcript().name == SAMPLE_SUBTASK and type != "solver":
        before = state_jsonable()
        yield
        after = state_jsonable()

        changes = json_changes(before, after)
        if changes:
            transcript()._event(StateEvent(changes=changes))
    else:
        yield


def init_transcript(transcript: Transcript) -> None:
    _transcript.set(transcript)


_transcript: ContextVar[Transcript] = ContextVar(
    "subtask_transcript", default=Transcript()
)


CONTENT_PROTOCOL = "tc://"


def eval_events(events: list[Event]) -> EvalEvents:
    content: dict[str, str] = {}

    def content_fn(text: str) -> str:
        if len(text) > 50:
            hash = mm3_hash(text)
            content[hash] = text
            return f"{CONTENT_PROTOCOL}{hash}"
        else:
            return text

    events = walk_events(events, content_fn)

    return EvalEvents(events=events, content=content)


def eval_events_with_content(events: EvalEvents) -> list[Event]:
    def content_fn(text: str) -> str:
        if text.startswith(CONTENT_PROTOCOL):
            return events.content.get(text, text)
        else:
            return text

    return walk_events(events.events, content_fn)


def walk_events(events: list[Event], content_fn: Callable[[str], str]) -> list[Event]:
    return [walk_event(event, content_fn) for event in events]


def walk_event(event: Event, content_fn: Callable[[str], str]) -> Event:
    if isinstance(event, ModelEvent):
        return walk_model_event(event, content_fn)
    elif isinstance(event, StateEvent):
        return walk_state_event(event, content_fn)
    else:
        return event


def walk_model_event(event: ModelEvent, content_fn: Callable[[str], str]) -> ModelEvent:
    return event.model_copy(
        update=dict(
            input=[walk_chat_message(message, content_fn) for message in event.input],
            output=walk_model_output(event.output, content_fn),
        ),
    )


def walk_model_output(
    output: ModelOutput, content_fn: Callable[[str], str]
) -> ModelOutput:
    return output.model_copy(
        update=dict(
            choices=[
                choice.model_copy(
                    update=dict(message=walk_chat_message(choice.message, content_fn))
                )
                for choice in output.choices
            ]
        )
    )


def walk_state_event(event: StateEvent, content_fn: Callable[[str], str]) -> StateEvent:
    event = event.model_copy(
        update=dict(
            changes=[
                walk_state_json_change(change, content_fn) for change in event.changes
            ]
        )
    )
    return event


def walk_state_json_change(
    change: JsonChange, content_fn: Callable[[str], str]
) -> JsonChange:
    if change.path.startswith("/messages") or change.path.startswith("/output"):
        return change.model_copy(
            update=dict(value=walk_json_value(change.value, content_fn))
        )
    else:
        return change


def walk_json_value(value: JsonValue, content_fn: Callable[[str], str]) -> JsonValue:
    if isinstance(value, str):
        return content_fn(value)
    elif isinstance(value, list):
        return [walk_json_value(v, content_fn) for v in value]
    elif isinstance(value, dict):
        updates: dict[str, JsonValue] = {}
        for k, v in value.items():
            if k in ["content", "message", "text", "image", "value"]:
                updates[k] = walk_json_value(v, content_fn)
        if updates:
            value = value.copy()
            value.update(updates)
        return value
    else:
        return value


def walk_chat_message(
    message: ChatMessage, content_fn: Callable[[str], str]
) -> ChatMessage:
    if isinstance(message.content, str):
        return message.model_copy(update=dict(content=content_fn(message.content)))
    else:
        return message.model_copy(
            update=dict(
                content=[
                    walk_content(content, content_fn) for content in message.content
                ]
            )
        )


def walk_content(content: Content, content_fn: Callable[[str], str]) -> Content:
    if isinstance(content, ContentText):
        return content.model_copy(update=dict(text=content_fn(content.text)))
    elif isinstance(content, ContentImage):
        return content.model_copy(update=dict(image=content_fn(content.image)))


def mm3_hash(message: str) -> str:
    # Generate the 128-bit hash as two 64-bit integers
    h1, h2 = mmh3.hash64(message.encode("utf-8"))

    # Convert to unsigned integers and then to hexadecimal
    return f"{h1 & 0xFFFFFFFFFFFFFFFF:016x}{h2 & 0xFFFFFFFFFFFFFFFF:016x}"