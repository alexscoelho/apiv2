import logging, datetime
from django.shortcuts import render
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import Event, EventType, EventCheckin
from breathecode.admissions.models import Academy
from rest_framework.decorators import api_view, permission_classes
from .serializers import (
    EventSerializer, EventSmallSerializer, EventTypeSerializer, EventCheckinSerializer,
    EventSmallSerializerNoAcademy
) 
from rest_framework.response import Response
from rest_framework.views import APIView
# from django.http import HttpResponse
from rest_framework.response import Response
from breathecode.utils import capable_of
from rest_framework.decorators import renderer_classes
from breathecode.renderers import PlainTextRenderer
from breathecode.services.eventbrite import Eventbrite
from .tasks import async_eventbrite_webhook
from breathecode.utils import ValidationException


logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_events(request):
    items = Event.objects.all()
    lookup = {}

    if 'city' in request.GET:
        city = request.GET.get('city')
        lookup['venue__city__iexact'] = city

    if 'country' in request.GET:
        value = request.GET.get('country')
        lookup['venue__country__iexact'] = value
        
    if 'type' in request.GET:
        value = request.GET.get('type')
        lookup['event_type__slug'] = value

    if 'zip_code' in request.GET:
        value = request.GET.get('zip_code')
        lookup['venue__zip_code'] = value

    if 'academy' in request.GET:
        value = request.GET.get('academy')
        lookup['academy__slug__in']=value.split(",")

    lookup['starting_at__gte'] = timezone.now()
    if 'past' in request.GET:
        if request.GET.get('past') == "true":
            lookup.pop("starting_at__gte")
            lookup['starting_at__lte'] = timezone.now()
        
    items = items.filter(**lookup).order_by('starting_at')
    
    serializer = EventSmallSerializer(items, many=True)
    return Response(serializer.data)


class EventView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    def get(self, request, format=None):
        
        items = Event.objects.all()
        lookup = {}

        if 'city' in self.request.GET:
            city = self.request.GET.get('city')
            lookup['venue__city__iexact'] = city

        if 'country' in self.request.GET:
            value = self.request.GET.get('city')
            lookup['venue__country__iexact'] = value

        if 'zip_code' in self.request.GET:
            value = self.request.GET.get('city')
            lookup['venue__zip_code'] = value

        lookup['starting_at__gte'] = timezone.now()
        if 'past' in self.request.GET:
            if self.request.GET.get('past') == "true":
                lookup.pop("starting_at__gte")
                lookup['starting_at__lte'] = timezone.now()
            
        items = items.filter(**lookup).order_by('-created_at')
        
        serializer = EventSmallSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AcademyEventView(APIView):
    """
    List all snippets, or create a new snippet.
    """

    @capable_of('read_event')
    def get(self, request, format=None, academy_id=None, event_id=None):
    
        if event_id is not None:
            single_event = Event.objects.filter(id=event_id,academy__id=academy_id).first()
            if single_event is None:
                raise ValidationException("Event not found", 404)

            serializer = EventSmallSerializer(single_event, many=False)
            return Response(serializer.data)
        
        items = Event.objects.filter(academy__id=academy_id)
        lookup = {}

        if 'city' in self.request.GET:
            city = self.request.GET.get('city')
            lookup['venue__city__iexact'] = city

        if 'country' in self.request.GET:
            value = self.request.GET.get('city')
            lookup['venue__country__iexact'] = value

        if 'zip_code' in self.request.GET:
            value = self.request.GET.get('city')
            lookup['venue__zip_code'] = value

        if 'upcoming' in self.request.GET:
            lookup['starting_at__gte'] = timezone.now()
        elif 'past' in self.request.GET:
            if self.request.GET.get('past') == "true":
                lookup.pop("starting_at__gte")
                lookup['starting_at__lte'] = timezone.now()
            
        items = items.filter(**lookup).order_by('-starting_at')
        
        serializer = EventSmallSerializerNoAcademy(items, many=True)
        return Response(serializer.data)

    @capable_of('crud_event')
    def post(self, request, format=None, academy_id=None):

        academy = Academy.objects.filter(id=academy_id).first()
        if academy is None:
            raise ValidationException(f"Academy {academy_id} not found")

        serializer = EventSerializer(data={ **request.data, "academy": academy.id })
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @capable_of('crud_event')
    def put(self, request, academy_id=None, event_id=None):

        already = Event.objects.filter(id=event_id,academy__id=academy_id).first()
        if already is None:
            raise ValidationException(f"Event not found for this academy {academy_id}")

        serializer = EventSerializer(already, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventTypeView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    def get(self, request, format=None):
        
        items = EventType.objects.all()
        lookup = {}

        if 'academy' in self.request.GET:
            value = self.request.GET.get('academy')
            lookup['academy__slug'] = value
            
        items = items.filter(**lookup).order_by('-created_at')
        
        serializer = EventTypeSerializer(items, many=True)
        return Response(serializer.data)


class EventCheckinView(APIView):
    """
    List all snippets, or create a new snippet.
    """
    @capable_of('read_eventcheckin')
    def get(self, request, format=None, academy_id=None):
        
        items = EventCheckin.objects.filter(event__academy__id=academy_id)
        lookup = {}

        if 'status' in self.request.GET:
            value = self.request.GET.get('status')
            lookup['status'] = value

        if 'event' in self.request.GET:
            value = self.request.GET.get('event')
            lookup['event__id'] = value

        start = request.GET.get('start', None)
        if start is not None:
            start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date()
            items = items.filter(created_at__gte=start_date)

        end = request.GET.get('end', None)
        if end is not None:
            end_date = datetime.datetime.strptime(end, "%Y-%m-%d").date()
            items = items.filter(created_at__lte=end_date)
            
        items = items.filter(**lookup).order_by('-created_at')
        
        serializer = EventCheckinSerializer(items, many=True)
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
@renderer_classes([PlainTextRenderer])
def eventbrite_webhook(request, organization_id):
    webhook = Eventbrite.add_webhook_to_log(request.data, organization_id)

    if webhook:
        async_eventbrite_webhook.delay(webhook.id)
    else:
        logger.debug('One request cannot be parsed, maybe you should update `Eventbrite'
            '.add_webhook_to_log`')
        logger.debug(request.data)

    # async_eventbrite_webhook(request.data)
    return Response('ok', content_type='text/plain')
