from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .google_calendar import GoogleCalendarAPI


class Category(models.Model):
    """Category for inventory items"""
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    name = models.CharField(max_length=200, unique=True)
    quantity = models.PositiveIntegerField()
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='items'
    )
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True, null=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='inventory_items'
    )

    class Meta:
        ordering = ['-date_created']
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory Items'

    def __str__(self):
        return f"{self.name} ({self.quantity})"

    def is_low_stock(self, threshold=5):
        """Check if item is in low stock"""
        return self.quantity <= threshold


class LabRoom(models.Model):
    """Lab room model"""
    name = models.CharField(max_length=100, unique=True)
    calendar_id = models.CharField(
        max_length=255,
        blank=True,  # Keep it nullable
        default='',
        help_text="Google Calendar ID for this room (optional)"
    )
    description = models.TextField(blank=True)
    is_available = models.BooleanField(default=True)
    capacity = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of people allowed"
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Lab Room'
        verbose_name_plural = 'Lab Rooms'

    def __str__(self):
        return self.name

    def get_upcoming_reservations(self):
        """Get all upcoming reservations for this room"""
        return self.reservations.filter(
            start_time__gte=timezone.now(),
            status='confirmed'
        ).order_by('start_time')

    def is_available_at(self, start_time, end_time):
        """Check if room is available during specified time period"""
        conflicting_reservations = self.reservations.filter(
            status='confirmed',
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        return not conflicting_reservations.exists()


class Reservation(models.Model):
    """Reservation model for lab rooms"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    room_key = models.CharField(
        max_length=50,
        default='room1',  # Set default value to 'room1'
        help_text="The room identifier (e.g., 'room1', 'room2')"
    )
    calendar_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Google Calendar ID for the room"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    purpose = models.TextField(
        help_text="Purpose of the reservation"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    event_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Google Calendar event ID"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']
        verbose_name = 'Reservation'
        verbose_name_plural = 'Reservations'

    def __str__(self):
        """String representation of the reservation"""
        room_name = settings.LAB_ROOMS[self.room_key]['name']
        return f"{room_name} - {self.user.username} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Set calendar_id from settings if not already set
        if not self.calendar_id and self.room_key in settings.LAB_ROOMS:
            self.calendar_id = settings.LAB_ROOMS[self.room_key]['calendar_id']

        # Create or update Google Calendar event
        if self.status == 'confirmed':
            calendar_api = GoogleCalendarAPI()
            event_summary = f"Room Reservation - {self.room_name}"
            event_description = f"Reserved by: {self.user.username}\nPurpose: {self.purpose}"

            try:
                if is_new or not self.event_id:
                    # Create new event
                    self.event_id = calendar_api.create_event(
                        self.calendar_id,
                        event_summary,
                        self.start_time,
                        self.end_time,
                        event_description
                    )
                else:
                    # Update existing event
                    calendar_api.update_event(
                        self.calendar_id,
                        self.event_id,
                        event_summary,
                        self.start_time,
                        self.end_time,
                        event_description
                    )
            except Exception as e:
                raise ValidationError(f"Calendar sync failed: {str(e)}")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Delete Google Calendar event if it exists
        if self.event_id:
            try:
                calendar_api = GoogleCalendarAPI()
                calendar_api.delete_event(self.calendar_id, self.event_id)
            except Exception as e:
                # Log the error but continue with deletion
                print(f"Failed to delete Google Calendar event: {str(e)}")

        super().delete(*args, **kwargs)

    def cancel(self):
        """Cancel the reservation"""
        if self.status != 'cancelled':
            # Delete Google Calendar event if it exists
            if self.event_id:
                try:
                    calendar_api = GoogleCalendarAPI()
                    calendar_api.delete_event(self.calendar_id, self.event_id)
                    self.event_id = ''
                except Exception as e:
                    raise ValidationError(f"Failed to cancel calendar event: {str(e)}")

            self.status = 'cancelled'
            self.save()
            return True
        return False

    def clean(self):
        """Validate the reservation"""
        if not self.start_time or not self.end_time:
            raise ValidationError("Both start and end times are required.")

        # Check if room_key is valid
        if self.room_key not in settings.LAB_ROOMS:
            raise ValidationError("Invalid room selection.")

        # Check if end time is after start time
        if self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

        # Check if start time is in the future
        if self.start_time < timezone.now():
            raise ValidationError("Cannot create reservations in the past.")

        # Check if duration is within allowed limits (e.g., 4 hours maximum)
        max_duration = timedelta(hours=4)
        if (self.end_time - self.start_time) > max_duration:
            raise ValidationError("Reservation duration cannot exceed 4 hours.")

        # Check for conflicts with existing reservations
        conflicts = Reservation.objects.filter(
            room_key=self.room_key,
            status='confirmed',
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        )

        # Exclude current reservation when checking conflicts (for updates)
        if self.pk:
            conflicts = conflicts.exclude(pk=self.pk)

        if conflicts.exists():
            raise ValidationError("This time slot conflicts with an existing reservation.")

    @property
    def room_name(self):
        """Get the friendly name of the room"""
        return settings.LAB_ROOMS[self.room_key]['name']

    @property
    def duration(self):
        """Get the duration of the reservation in hours"""
        return (self.end_time - self.start_time).total_seconds() / 3600

    @property
    def is_active(self):
        """Check if the reservation is currently active"""
        now = timezone.now()
        return (
                self.status == 'confirmed' and
                self.start_time <= now <= self.end_time
        )

    @classmethod
    def get_upcoming_reservations(cls, room_key):
        """Get all upcoming reservations for a specific room"""
        return cls.objects.filter(
            room_key=room_key,
            status='confirmed',
            end_time__gte=timezone.now()
        ).order_by('start_time')

    @classmethod
    def get_user_reservations(cls, user):
        """Get all reservations for a specific user"""
        return cls.objects.filter(
            user=user
        ).order_by('-start_time')

    @classmethod
    def is_room_available(cls, room_key, start_time, end_time):
        """Check if a room is available during the specified time period"""
        conflicts = cls.objects.filter(
            room_key=room_key,
            status='confirmed',
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        return not conflicts.exists()
