from celery import shared_task


@shared_task
def tournament_lifecycle_task():
    """Periodic sweep: open registration and auto-start tournaments whose
    registration window has elapsed. Runs every minute via Celery beat."""
    from .services import run_tournament_lifecycle

    return run_tournament_lifecycle()
