from rest_framework import serializers


class WorkspaceRelatedField(serializers.PrimaryKeyRelatedField):
    """
    A primary-key field limited to rows of the request's workspace. It reads the workspace when it
    validates, so it also works inside nested serializers (whose __init__ runs before any context exists).
    """

    def __init__(self, model, **kwargs):
        self.model = model
        kwargs.setdefault("queryset", model.objects.all())
        super().__init__(**kwargs)

    def get_queryset(self):
        workspace = self.context.get("workspace")
        qs = self.model.objects.all()
        if workspace is None:
            return qs.none()
        from .scoping import scope_queryset

        request = self.context.get("request")
        return scope_queryset(qs.filter(workspace=workspace), request) if request is not None else qs.filter(workspace=workspace)
