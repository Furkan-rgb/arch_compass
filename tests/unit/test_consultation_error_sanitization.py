from archcompass.domain.errors import ModelOutputValidationError
from archcompass.workflows.consultation import ConsultationWorkflow


def test_safe_synthesis_coverage_error_is_preserved() -> None:
    error = ModelOutputValidationError(
        "Final synthesis must provide findings for every concern cluster"
    )

    assert ConsultationWorkflow._sanitize_error(error, None) == (
        "ModelOutputValidationError: "
        "Final synthesis must provide findings for every concern cluster"
    )


def test_unallowlisted_model_validation_detail_remains_hidden() -> None:
    error = ModelOutputValidationError("provider-authored detail")

    assert ConsultationWorkflow._sanitize_error(error, None) == (
        "ModelOutputValidationError: Structured model output failed validation"
    )
