from google.oauth2 import service_account
from googleapiclient.discovery import build
from django.conf import settings

class GoogleCalendarAPI:
    def __init__(self):
        credentials = service_account.Credentials.from_service_account_info(
            settings.GOOGLE_CALENDAR_API_CREDENTIALS,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        self.service = build('calendar', 'v3', credentials=credentials)

    def create_event(self, calendar_id, summary, start_time, end_time, description=None):
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': settings.TIME_ZONE,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': settings.TIME_ZONE,
            },
        }

        try:
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            return event['id']
        except Exception as e:
            raise Exception(f"Failed to create Google Calendar event: {str(e)}")

    def update_event(self, calendar_id, event_id, summary, start_time, end_time, description=None):
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': settings.TIME_ZONE,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': settings.TIME_ZONE,
            },
        }

        try:
            self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
        except Exception as e:
            raise Exception(f"Failed to update Google Calendar event: {str(e)}")

    def delete_event(self, calendar_id, event_id):
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
        except Exception as e:
            raise Exception(f"Failed to delete Google Calendar event: {str(e)}")