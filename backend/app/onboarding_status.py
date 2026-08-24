from .onboarding_service import get_onboarding_checklist


def evaluate_onboarding_status(
    onboarding_id: int | str,
    db=None,
):
    checklist = get_onboarding_checklist(onboarding_id)
    return {
        "onboarding_id": checklist["onboarding_id"],
        "status": checklist["onboarding_status"],
        "documents": checklist["documents"],
    }