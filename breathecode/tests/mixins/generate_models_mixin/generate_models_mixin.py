"""
Collections of mixins used to login in authorize microservice
"""
from breathecode.tests.mixins.generate_models_mixin.assignments_models_mixin import AssignmentsModelsMixin
from datetime import datetime
from mixer.backend.django import mixer
from .authenticate_models_mixin import AuthenticateMixin
from .admissions_models_mixin import AdmissionsModelsMixin
from .auth_mixin import AuthMixin

class GenerateModelsMixin(AuthMixin, AssignmentsModelsMixin,
        AdmissionsModelsMixin, AuthenticateMixin):

    def __flow_wrapper__(self, *args, **kwargs):
        models = {}

        if 'models' in kwargs:
            models = kwargs['models'].copy()
            del kwargs['models']

        for func in args:
            models = func(models=models, **kwargs)

        return models

    def __flow__(self, *args):
        def inner_wrapper(**kwargs):
            return self.__flow_wrapper__(*args, **kwargs)

        return inner_wrapper

    def generate_models(self, models={}, **kwargs):
        self.maxDiff = None
        models = models.copy()

        fn = self.__flow__(
            self.generate_credentials,
            self.generate_assignments_models,
            self.generate_admissions_models,
            self.generate_authenticate_models
        )

        return fn(models=models, **kwargs)
