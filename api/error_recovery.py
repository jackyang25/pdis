"""Recovery copy for known failures, shared by streamed tool runs.

Classify concrete exception types/statuses, never finished error prose. Unknown
errors retain their original detail without promising that retrying can help.
"""

import anthropic
import openai

from shared.errors import ModelResponseError

_TRY_AGAIN = (
    "Try again. If the issue persists, report it through Feedback "
    "with this error message."
)


def recovery_guidance(error: Exception) -> str | None:
    if isinstance(error, (ModelResponseError, openai.APIConnectionError, anthropic.APIConnectionError)):
        return _TRY_AGAIN
    if isinstance(error, (openai.APIStatusError, anthropic.APIStatusError)):
        status = error.status_code
        if status == 429:
            return "Wait a moment, then try again. If the limit persists, contact your administrator."
        if status in (408, 409, 500, 502, 503, 504, 529):
            return _TRY_AGAIN
        if status == 413:
            return (
                "The analysis request was too large. Report it through Feedback "
                "with this error message; rerunning unchanged may hit the same limit."
            )
        if status in (401, 403):
            return "Contact your administrator to check access to the model service."
    return None
