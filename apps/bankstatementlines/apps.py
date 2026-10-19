from django.apps import AppConfig


class BankstatementlinesConfig(AppConfig):
    name = "apps.bankstatementlines"
    label = "bankstatementlines"

    def ready(self):
        from . import services  # noqa: F401  (registers the signal that frees matched lines)
