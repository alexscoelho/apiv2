import logging, re, pytz
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.models import AnonymousUser
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import JSONParser
from django.contrib.auth.models import User
from .serializers import (
    AcademySerializer, CohortSerializer, CertificateSerializer,
    GetCohortSerializer, UserSerializer, CohortUserSerializer,
    GETCohortUserSerializer, CohortUserPUTSerializer, CohortPUTSerializer,
    CohortUserPOSTSerializer, UserDJangoRestSerializer, UserMeSerializer
)
from .models import Academy, City, CohortUser, Certificate, Cohort, Country, STUDENT, DELETED
from breathecode.authenticate.models import ProfileAcademy
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from breathecode.utils import Cache, localize_query, capable_of, ValidationException
from django.http import QueryDict
from django.db.utils import IntegrityError
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied, ValidationError
from breathecode.assignments.models import Task

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_timezones(request, id=None):
    # timezones = [(x, x) for x in pytz.common_timezones]
    return Response(pytz.common_timezones)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_cohorts(request, id=None):

    items = Cohort.objects.all()

    if isinstance(request.user, AnonymousUser) == False:
        # filter only to the local academy
        items = localize_query(items, request)

    upcoming = request.GET.get('upcoming', None)
    if upcoming == 'true':
        now = timezone.now()
        items = items.filter(kickoff_date__gte=now)

    academy = request.GET.get('academy', None)
    if academy is not None:
        items = items.filter(academy__slug__in=academy.split(","))

    location = request.GET.get('location', None)
    if location is not None:
        items = items.filter(academy__slug__in=location.split(","))

    items = items.order_by('kickoff_date')
    serializer = GetCohortSerializer(items, many=True)
    return Response(serializer.data)

class UserMeView(APIView):
    def get(self, request, format=None):

        logger.error("Get me just called")
        try:
            if isinstance(request.user, AnonymousUser):
                raise PermissionDenied("There is not user")    

        except User.DoesNotExist:
            raise PermissionDenied("You don't have a user")

        users = UserMeSerializer(request.user)
        return Response(users.data)

# Create your views here.
class AcademyView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    def get(self, request, format=None):
        items = Academy.objects.all()
        serializer = AcademySerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        data = {}

        for key in request.data:
            data[key] = request.data.get(key)

        serializer = AcademySerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UserDJangoRestSerializer(request.user, data=request.data, context={ "request": request })
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CohortUserView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    def get(self, request, format=None):
        items = CohortUser.objects.all()

        roles = request.GET.get('roles', None)
        if roles is not None:
            items = items.filter(role__in=roles.split(","))

        finantial_status = request.GET.get('finantial_status', None)
        if finantial_status is not None:
            items = items.filter(finantial_status__in=finantial_status.split(","))

        educational_status = request.GET.get('educational_status', None)
        if educational_status is not None:
            items = items.filter(educational_status__in=educational_status.split(","))

        academy = request.GET.get('academy', None)
        if academy is not None:
            items = items.filter(cohort__academy__slug__in=academy.split(","))

        cohorts = request.GET.get('cohorts', None)
        if cohorts is not None:
            items = items.filter(cohort__slug__in=cohorts.split(","))

        users = request.GET.get('users', None)
        if users is not None:
            items = items.filter(user__id__in=users.split(","))

        serializer = GETCohortUserSerializer(items, many=True)
        return Response(serializer.data)

    def count_certificates_by_cohort(self, cohort, user_id):
        return (CohortUser.objects.filter(user_id=user_id, cohort__certificate=cohort.certificate)
            .exclude(educational_status='POSTPONED').count())

    def validations(self, request, cohort_id=None, user_id=None, matcher=None,
            disable_cohort_user_just_once=False, disable_certificate_validations=False):

        if user_id is None:
            user_id = request.data.get('user')

        if cohort_id is None or user_id is None:
            raise ValidationException("Missing cohort_id or user_id", code=400)

        if User.objects.filter(id=user_id).count() == 0:
            raise ValidationException("invalid user_id", code=400)

        cohort = Cohort.objects.filter(id=cohort_id)
        if not cohort:
            raise ValidationException("invalid cohort_id", code=400)

        cohort = localize_query(cohort, request).first() # only from this academy

        if cohort is None:
            logger.debug(f"Cohort not be found in related academies")
            raise ValidationException('Specified cohort not be found')

        if not disable_cohort_user_just_once and CohortUser.objects.filter(user_id=user_id,
                cohort_id=cohort_id).count():
            raise ValidationException('That user already exists in this cohort')

        if not disable_certificate_validations and self.count_certificates_by_cohort(
                cohort, user_id) > 0:
            raise ValidationException('This student is already in another cohort for the same certificate, please mark him/her hi educational status on this prior cohort as POSTPONED before cotinuing')

        role = request.data.get('role')
        if role == 'TEACHER' and CohortUser.objects.filter(role=role, cohort_id=cohort_id).exclude(user__id__in=[user_id]).count():
            raise ValidationException('There can only be one main instructor in a cohort')

        cohort_user = CohortUser.objects.filter(user__id=user_id, cohort__id=cohort_id).first()

        is_graduated = request.data.get('educational_status') == 'GRADUATED'
        is_late = (True if cohort_user and cohort_user.finantial_status == 'LATE' else request.data
            .get('finantial_status') == 'LATE')
        if is_graduated and is_late:
            raise ValidationException(('Cannot be marked as `GRADUATED` if its financial '
                'status is `LATE`'))

        has_tasks = Task.objects.filter(user_id=user_id, task_status='PENDING',
            task_type='PROJECT').count()
        if is_graduated and has_tasks:
            raise ValidationException('User has tasks with status pending the educational status cannot be GRADUATED')

        data = {}

        for key in request.data:
            data[key] = request.data.get(key)

        data['cohort'] = cohort_id

        return {
            'data': data,
            'cohort': cohort,
            'cohort_user': cohort_user,
        }

    def post(self, request, cohort_id=None):
        validations = self.validations(request, cohort_id, matcher="cohort__academy__in")

        serializer = CohortUserSerializer(data=validations['data'], context=validations['data'])
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, cohort_id=None, user_id=None):
        validations = self.validations(request, cohort_id, user_id, "cohort__academy__in",
            disable_cohort_user_just_once=True, disable_certificate_validations=True)

        serializer = CohortUserPUTSerializer(validations['cohort_user'], data=validations['data'],
            context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, cohort_id=None, user_id=None):

        if cohort_id is None or user_id is None:
            raise ValidationException("Missing user_id or cohort_id", code=400)

        academy_ids = ProfileAcademy.objects.filter(user=request.user).values_list('academy__id',
            flat=True)

        cu = CohortUser.objects.filter(user__id=user_id,cohort__id=cohort_id,
            cohort__academy__id__in=academy_ids).first()
        if cu is None:
            raise ValidationException('Specified cohort and user could not be found')

        cu.delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)

class AcademyCohortUserView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    @capable_of('read_cohort')
    def get(self, request, format=None, cohort_id=None, user_id=None, academy_id=None):

        if user_id is not None:
            item = CohortUser.objects.filter(cohort__academy__id=academy_id, user__id=user_id, cohort__id=cohort_id).first()
            if item is None:
                raise ValidationException("Cohort user not found", 404)
            serializer = GETCohortUserSerializer(item, many=False)
            return Response(serializer.data)

        items = CohortUser.objects.filter(cohort__academy__id=academy_id)

        try:

            roles = request.GET.get('roles', None)
            if roles is not None:
                items = items.filter(role__in=roles.split(","))

            finantial_status = request.GET.get('finantial_status', None)
            if finantial_status is not None:
                items = items.filter(finantial_status__in=finantial_status.split(","))

            educational_status = request.GET.get('educational_status', None)
            if educational_status is not None:
                items = items.filter(educational_status__in=educational_status.split(","))

            cohorts = request.GET.get('cohorts', None)
            if cohorts is not None:
                items = items.filter(cohort__slug__in=cohorts.split(","))

            users = request.GET.get('users', None)
            if users is not None:
                items = items.filter(user__id__in=users.split(","))
        except Exception as e:
            raise ValidationException(str(e), 400)

        serializer = GETCohortUserSerializer(items, many=True)
        return Response(serializer.data)

    def count_certificates_by_cohort(self, cohort, user_id):
        return (CohortUser.objects.filter(user_id=user_id, cohort__certificate=cohort.certificate)
            .exclude(educational_status='POSTPONED').count())

    def validations(self, request, cohort_id=None, user_id=None, matcher=None,
            disable_cohort_user_just_once=False, disable_certificate_validations=False):

        if user_id is None:
            user_id = request.data.get('user')

        if cohort_id is None or user_id is None:
            raise ValidationException("Missing cohort_id or user_id", code=400)

        if User.objects.filter(id=user_id).count() == 0:
            raise ValidationException("invalid user_id", code=400)

        cohort = Cohort.objects.filter(id=cohort_id)
        if not cohort:
            raise ValidationException("invalid cohort_id", code=400)

        cohort = localize_query(cohort, request).first() # only from this academy

        if cohort is None:
            logger.debug(f"Cohort not be found in related academies")
            raise ValidationException('Specified cohort not be found')

        if not disable_cohort_user_just_once and CohortUser.objects.filter(user_id=user_id,
                cohort_id=cohort_id).count():
            raise ValidationException('That user already exists in this cohort')

        if not disable_certificate_validations and self.count_certificates_by_cohort(
                cohort, user_id) > 0:
            raise ValidationException('This student is already in another cohort for the same certificate, please mark him/her hi educational status on this prior cohort as POSTPONED before cotinuing')

        role = request.data.get('role')
        if role == 'TEACHER' and CohortUser.objects.filter(role=role, cohort_id=cohort_id).exclude(user__id__in=[user_id]).count():
            raise ValidationException('There can only be one main instructor in a cohort')

        cohort_user = CohortUser.objects.filter(user__id=user_id, cohort__id=cohort_id).first()

        is_graduated = request.data.get('educational_status') == 'GRADUATED'
        is_late = (True if cohort_user and cohort_user.finantial_status == 'LATE' else request.data
            .get('finantial_status') == 'LATE')
        if is_graduated and is_late:
            raise ValidationException(('Cannot be marked as `GRADUATED` if its financial '
                'status is `LATE`'))

        has_tasks = Task.objects.filter(user_id=user_id, task_status='PENDING',
            task_type='PROJECT').count()
        if is_graduated and has_tasks:
            raise ValidationException('User has tasks with status pending the educational status cannot be GRADUATED')

        data = {}

        for key in request.data:
            data[key] = request.data.get(key)

        data['cohort'] = cohort_id

        return {
            'data': data,
            'cohort': cohort,
            'cohort_user': cohort_user,
        }

    @capable_of('crud_cohort')
    def post(self, request, cohort_id=None, academy_id=None):
        validations = self.validations(request, cohort_id, matcher="cohort__academy__in")

        serializer = CohortUserSerializer(data=validations['data'], context=validations['data'])
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @capable_of('crud_cohort')
    def put(self, request, cohort_id=None, user_id=None, academy_id=None):
        validations = self.validations(request, cohort_id, user_id, "cohort__academy__in",
            disable_cohort_user_just_once=True, disable_certificate_validations=True)

        serializer = CohortUserPUTSerializer(validations['cohort_user'], data=validations['data'],
            context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @capable_of('crud_cohort')
    def delete(self, request, cohort_id=None, user_id=None, academy_id=None):

        if cohort_id is None or user_id is None:
            raise ValidationException("Missing user_id or cohort_id", code=400)

        cu = CohortUser.objects.filter(user__id=user_id,cohort__id=cohort_id, cohort__academy__id=academy_id).first()
        if cu is None:
            raise ValidationException('Specified cohort and user could not be found')

        cu.delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)

class AcademyCohortView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    permission_classes = [IsAuthenticated]

    def cache(self):
        return Cache('academy_cohort')

    @capable_of('read_cohort')
    def get(self, request, cohort_id=None, academy_id=None):
        if cohort_id is not None:
            item = None
            if str.isnumeric(cohort_id):
                item = Cohort.objects.filter(id=int(cohort_id), academy__id=academy_id).first()
            else:
                item = Cohort.objects.filter(slug=cohort_id, academy__id=academy_id).first()

            if item is None:
                return Response(status=status.HTTP_404_NOT_FOUND)

            serializer = GetCohortSerializer(item, many=False)
            return Response(serializer.data, status=status.HTTP_200_OK)

        items = Cohort.objects.filter(academy__id=academy_id)
        upcoming = request.GET.get('upcoming', None)
        if upcoming == 'true':
            now = timezone.now()
            items = items.filter(kickoff_date__gte=now)

        academy = request.GET.get('academy', None)
        if academy is not None:
            items = items.filter(academy__slug__in=academy.split(","))

        location = request.GET.get('location', None)
        if location is not None:
            items = items.filter(academy__slug__in=location.split(","))

        serializer = GetCohortSerializer(items, many=True)
        return Response(serializer.data)

    @capable_of('crud_cohort')
    def post(self, request, academy_id=None):
        if request.data.get('academy') or request.data.get('academy_id'):
            raise ParseError(detail='academy and academy_id field is not allowed')

        print('======================================================')
        print('======================================================')
        print('======================================================')
        print(self.cache().keys(all=True))
        print('======================================================', 'POST')

        academy = Academy.objects.filter(id=academy_id).first()
        if academy is None:
            raise ValidationError(f'Academy {academy_id} not found')

        certificate_id = request.data.get('certificate')
        if certificate_id is None:
            raise ParseError(detail='certificate field is missing')

        certificate = Certificate.objects.filter(id=certificate_id).first()
        if certificate is None:
            raise ParseError(detail='specified certificate not be found')

        if request.data.get('current_day'):
            raise ParseError(detail='current_day field is not allowed')

        data = {
            'academy': academy,
            'current_day': 0,
        }

        for key in request.data:
            data[key] = request.data.get(key)

        data['certificate'] = certificate

        serializer = CohortSerializer(data=data, context=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @capable_of('crud_cohort')
    def put(self, request, cohort_id=None, academy_id=None):
        if cohort_id is None:
            raise ValidationException("Missing cohort_id", code=400)

        cohort = Cohort.objects.filter(id=cohort_id, academy__id=academy_id)
        cohort = localize_query(cohort, request).first() # only from this academy
        if cohort is None:
            logger.debug(f"Cohort not be found in related academies")
            raise ValidationException('Specified cohort not be found')
        
        serializer = CohortPUTSerializer(cohort, data=request.data, context={ "request": request, "cohort_id": cohort_id })
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @capable_of('crud_cohort')
    def delete(self, request, cohort_id=None, academy_id=None):
        if cohort_id is None:
            raise ValidationException("Missing cohort_id", code=400)

        try:
            cohort = Cohort.objects.get(id=cohort_id, academy__id=academy_id)
        except Cohort.DoesNotExist:
            raise ValidationException("Cohort doesn't exist", code=400)

        cohort.stage = DELETED
        cohort.save()

        # STUDENT
        cohort_users = CohortUser.objects.filter(
            role=STUDENT,
            cohort__id=cohort_id
        )

        for cohort_user in cohort_users:
            cohort_user.delete()

        return Response(None, status=status.HTTP_204_NO_CONTENT)


class CertificateView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    def get(self, request, format=None):
        items = Certificate.objects.all()
        serializer = CertificateSerializer(items, many=True)
        return Response(serializer.data)
