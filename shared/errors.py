"""Typed failures whose meaning is known at the stage that raises them."""


class ModelResponseError(ValueError):
    """A model response remained unusable after the stage's allowed attempts.

    Input/configuration errors remain ordinary ValueErrors. Consumers must not
    infer retryability from their message or from the active stage's name.
    """

    code = "invalid_model_response"
