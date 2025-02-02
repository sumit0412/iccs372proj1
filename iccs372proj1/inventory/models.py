from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

class Category(models.Model):
    """Category for inventory items"""
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """Inventory item model"""
    name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    category = models.ForeignKey(
        Category,
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
    """Lab room reservation model"""
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
    lab_room = models.ForeignKey(
        LabRoom,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    purpose = models.TextField()
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
        return f"{self.lab_room.name} - {self.user.username} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    def clean(self):
        """Validate the reservation"""
        if self.start_time and self.end_time:
            # Check if end time is after start time
            if self.end_time <= self.start_time:
                raise ValidationError("End time must be after start time")

            # Check if start time is in the future
            if self.start_time < timezone.now():
                raise ValidationError("Cannot create reservations in the past")

            # Check if duration is within allowed limits (e.g., 4 hours maximum)
            max_duration = timedelta(hours=4)
            if (self.end_time - self.start_time) > max_duration:
                raise ValidationError("Reservation duration cannot exceed 4 hours")

            # Check for conflicts with existing reservations
            if not self.lab_room.is_available_at(self.start_time, self.end_time):
                raise ValidationError("Room is already reserved during this time period")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def duration(self):
        """Get reservation duration in hours"""
        return (self.end_time - self.start_time).total_seconds() / 3600

    @property
    def is_active(self):
        """Check if reservation is currently active"""
        now = timezone.now()
        return (
            self.status == 'confirmed' and
            self.start_time <= now <= self.end_time
        )